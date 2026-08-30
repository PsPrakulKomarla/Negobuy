"""Procurement Assurance router — contract review, order lifecycle tracking, invoice
verification, delivery confirmation. The AI analyzes and flags; humans approve.
No purchase/payment is ever auto-executed."""
import uuid
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db import get_db
from auth import get_current_user
import assurance_service
import audit

router = APIRouter(prefix="/api/missions", tags=["assurance"])

ORDER_STATES = ["AUTHORIZED", "ORDER_PLACED", "SUPPLIER_CONFIRMED", "PROCESSING",
                "READY_FOR_DISPATCH", "DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY",
                "DELIVERED", "DELIVERY_VERIFIED", "COMPLETED"]
ALT_STATES = ["DELIVERED_PENDING_VERIFICATION", "DELAY_RISK", "DELAYED", "DOCUMENT_MISSING",
              "PAYMENT_ACTION_REQUIRED", "SUPPLIER_RESPONSE_REQUIRED",
              "EXCEPTION_REQUIRES_HUMAN", "CANCELLED"]
ALL_STATES = ORDER_STATES + ALT_STATES


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _mission(db, mission_id, user):
    m = await db.missions.find_one(
        {"id": mission_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found")
    return m


# ------------------------- Contract review ------------------------- #
class ContractBody(BaseModel):
    contract_text: str
    offer_id: str | None = None


@router.post("/{mission_id}/contract/analyze")
async def analyze_contract(mission_id: str, body: ContractBody, user: dict = Depends(get_current_user)):
    db = get_db()
    mission = await _mission(db, mission_id, user)
    if not body.contract_text.strip():
        raise HTTPException(status_code=400, detail="Contract text required")
    offer = None
    if body.offer_id:
        offer = await db.offers.find_one({"id": body.offer_id, "mission_id": mission_id}, {"_id": 0})
    if not offer:
        offer = await db.offers.find_one(
            {"mission_id": mission_id, "status": "OPEN"}, {"_id": 0},
            sort=[("total_cost", 1)]) or {}
    analysis = await assurance_service.analyze_contract(
        mission, offer, body.contract_text, f"contract-{mission_id}")
    doc = {"id": uuid.uuid4().hex, "mission_id": mission_id,
           "organization_id": user["organization_id"], "offer_id": offer.get("id"),
           "analysis": analysis, "created_at": _now()}
    await db.contract_reviews.insert_one(dict(doc))
    doc.pop("_id", None)
    await audit.log_event(user["organization_id"], "contract_analyzed", mission_id=mission_id,
                          actor=user.get("name"),
                          detail=f"Recommendation: {analysis.get('recommendation')}")
    return doc


@router.get("/{mission_id}/contract")
async def latest_contract(mission_id: str, user: dict = Depends(get_current_user)):
    await _mission(get_db(), mission_id, user)
    doc = await get_db().contract_reviews.find_one(
        {"mission_id": mission_id, "organization_id": user["organization_id"]},
        {"_id": 0}, sort=[("created_at", -1)])
    return doc or {}


# ------------------------- Order lifecycle ------------------------- #
class AuthorizeBody(BaseModel):
    offer_id: str
    expected_delivery_date: str | None = None
    po_reference: str | None = None


def _health(order: dict) -> str:
    st = order.get("status")
    if st in ("DELIVERED", "DELIVERY_VERIFIED", "COMPLETED"):
        return "COMPLETED"
    if st in ("DELAYED", "EXCEPTION_REQUIRES_HUMAN"):
        return "DELAYED"
    if st in ("DELAY_RISK", "DOCUMENT_MISSING", "PAYMENT_ACTION_REQUIRED", "SUPPLIER_RESPONSE_REQUIRED"):
        return "ACTION_REQUIRED"
    edd = order.get("expected_delivery_date")
    if edd:
        try:
            if date.fromisoformat(edd[:10]) < date.today() and st not in ("DELIVERED", "COMPLETED"):
                return "ACTION_REQUIRED"
        except Exception:
            pass
    return "ON_TRACK"


@router.post("/{mission_id}/order/authorize")
async def authorize_order(mission_id: str, body: AuthorizeBody, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("owner", "admin", "buyer"):
        raise HTTPException(status_code=403, detail="You are not authorized to place orders.")
    db = get_db()
    mission = await _mission(db, mission_id, user)
    offer = await db.offers.find_one({"id": body.offer_id, "mission_id": mission_id}, {"_id": 0})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.get("within_authority") is False:
        raise HTTPException(status_code=400,
                            detail="This offer exceeds the authorized price and cannot be ordered.")
    if await db.orders.find_one({"mission_id": mission_id}):
        raise HTTPException(status_code=409, detail="An order already exists for this mission.")
    order = {
        "id": uuid.uuid4().hex, "mission_id": mission_id, "organization_id": user["organization_id"],
        "offer_id": offer["id"], "supplier": offer.get("vendor_name"),
        "product": mission.get("title"), "quantity": offer.get("quantity") or mission.get("quantity"),
        "unit_price": offer.get("negotiated_price"), "currency": offer.get("currency"),
        "total_cost": offer.get("total_cost") or (
            (offer.get("negotiated_price") or 0) * (offer.get("quantity") or mission.get("quantity") or 1)),
        "warranty": offer.get("warranty"), "payment_terms": offer.get("payment_terms"),
        "payment_status": "UNPAID", "delivery_location": mission.get("delivery_location"),
        "expected_delivery_date": body.expected_delivery_date, "po_reference": body.po_reference,
        "status": "AUTHORIZED", "authorized_by": user.get("name"),
        "events": [{"id": uuid.uuid4().hex, "status": "AUTHORIZED",
                    "note": f"Authorized by {user.get('name')}", "at": _now(), "source": "human"}],
        "created_at": _now(), "updated_at": _now(),
    }
    await db.orders.insert_one(dict(order))
    await db.missions.update_one({"id": mission_id}, {"$set": {"status": "PURCHASED"}})
    await audit.log_event(user["organization_id"], "order_authorized", mission_id=mission_id,
                          actor=user.get("name"), detail=f"Order authorized with {offer.get('vendor_name')}")
    order.pop("_id", None)
    order["health"] = _health(order)
    return order


@router.get("/{mission_id}/order")
async def get_order(mission_id: str, user: dict = Depends(get_current_user)):
    await _mission(get_db(), mission_id, user)
    order = await get_db().orders.find_one(
        {"mission_id": mission_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not order:
        return {}
    order["health"] = _health(order)
    return order


class StatusBody(BaseModel):
    status: str
    note: str | None = None
    expected_delivery_date: str | None = None
    source: str = "supplier_update"


@router.post("/{mission_id}/order/status")
async def update_status(mission_id: str, body: StatusBody, user: dict = Depends(get_current_user)):
    if body.status not in ALL_STATES:
        raise HTTPException(status_code=400, detail="Invalid order status")
    db = get_db()
    await _mission(db, mission_id, user)
    order = await db.orders.find_one({"mission_id": mission_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="No order for this mission")
    upd = {"status": body.status, "updated_at": _now()}
    if body.expected_delivery_date:
        upd["expected_delivery_date"] = body.expected_delivery_date
    event = {"id": uuid.uuid4().hex, "status": body.status, "note": body.note,
             "source": body.source, "at": _now()}
    await db.orders.update_one({"mission_id": mission_id},
                               {"$set": upd, "$push": {"events": event}})
    await audit.log_event(user["organization_id"], "order_status_update", mission_id=mission_id,
                          actor=user.get("name"), detail=f"{body.status}: {body.note or ''}")
    order = await db.orders.find_one({"mission_id": mission_id}, {"_id": 0})
    order["health"] = _health(order)
    return order


@router.get("/{mission_id}/order/timeline")
async def order_timeline(mission_id: str, user: dict = Depends(get_current_user)):
    await _mission(get_db(), mission_id, user)
    order = await get_db().orders.find_one({"mission_id": mission_id}, {"_id": 0})
    return {"events": (order or {}).get("events", []), "health": _health(order or {}),
            "status": (order or {}).get("status")}


# ------------------------- Invoice verification ------------------------- #
class InvoiceBody(BaseModel):
    invoice_text: str


@router.post("/{mission_id}/order/invoice")
async def verify_invoice(mission_id: str, body: InvoiceBody, user: dict = Depends(get_current_user)):
    db = get_db()
    await _mission(db, mission_id, user)
    order = await db.orders.find_one({"mission_id": mission_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="No order for this mission")
    if not body.invoice_text.strip():
        raise HTTPException(status_code=400, detail="Invoice text required")
    result = await assurance_service.verify_invoice(order, body.invoice_text, f"invoice-{mission_id}")
    await db.orders.update_one({"mission_id": mission_id},
                               {"$set": {"invoice_check": result, "updated_at": _now()},
                                "$push": {"events": {"id": uuid.uuid4().hex,
                                                     "status": "INVOICE_CHECKED",
                                                     "note": result.get("summary"),
                                                     "source": "assurance", "at": _now()}}})
    if result.get("has_discrepancies"):
        await db.orders.update_one({"mission_id": mission_id},
                                   {"$set": {"status": "PAYMENT_ACTION_REQUIRED"}})
    await audit.log_event(user["organization_id"], "invoice_verified", mission_id=mission_id,
                          actor=user.get("name"), detail=result.get("recommendation"))
    return result


# ------------------------- Delivery confirmation ------------------------- #
class DeliveryBody(BaseModel):
    action: str  # mark_delivered | verify | report_issue
    quantity_received: int | None = None
    condition: str | None = None
    notes: str | None = None


@router.post("/{mission_id}/order/delivery")
async def delivery(mission_id: str, body: DeliveryBody, user: dict = Depends(get_current_user)):
    db = get_db()
    await _mission(db, mission_id, user)
    order = await db.orders.find_one({"mission_id": mission_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="No order for this mission")
    now = _now()
    if body.action == "mark_delivered":
        new_status = "DELIVERED_PENDING_VERIFICATION"
        note = "Delivery reported — awaiting human verification."
    elif body.action == "verify":
        if user.get("role") not in ("owner", "admin", "buyer"):
            raise HTTPException(status_code=403, detail="Not authorized to verify delivery.")
        new_status = "COMPLETED"
        note = (f"Verified by {user.get('name')} — qty {body.quantity_received}, "
                f"condition {body.condition or 'ok'}.")
        await db.missions.update_one({"id": mission_id}, {"$set": {"status": "COMPLETED"}})
    elif body.action == "report_issue":
        new_status = "EXCEPTION_REQUIRES_HUMAN"
        note = f"Delivery issue reported: {body.notes or 'unspecified'}"
    else:
        raise HTTPException(status_code=400, detail="Invalid delivery action")
    await db.orders.update_one({"mission_id": mission_id},
                               {"$set": {"status": new_status, "updated_at": now},
                                "$push": {"events": {"id": uuid.uuid4().hex, "status": new_status,
                                                     "note": note, "source": "human", "at": now}}})
    await audit.log_event(user["organization_id"],
                          "delivery_verified" if body.action == "verify" else "delivery_update",
                          mission_id=mission_id, actor=user.get("name"), detail=note)
    order = await db.orders.find_one({"mission_id": mission_id}, {"_id": 0})
    order["health"] = _health(order)
    return order
