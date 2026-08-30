"""Stateful negotiation engine — ONE shared negotiation thread per (mission, vendor),
used by web sandbox, WhatsApp and phone. Extracts structured offer terms from every
supplier message, drives a state machine + decision engine, enforces authority, and
NEVER commits a purchase (human approval required)."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db import get_db
from auth import get_current_user
import ai_service
import vendor_memory
import audit

router = APIRouter(prefix="/api/missions", tags=["negotiation-engine"])
REAL_CHANNELS = {"whatsapp", "phone", "exotel"}
_OFFER_KEYS = ["unit_price", "quantity", "total_price", "shipping_included", "shipping_cost",
               "taxes", "fees", "delivery_days", "warranty", "payment_terms", "moq",
               "availability", "validity", "return_terms"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _constraints(mission: dict) -> dict:
    qty = mission.get("quantity") or 1
    budget = mission.get("budget") or 0
    mx = round(budget / qty, 2) if (budget and qty) else None
    return {"max_price": mx, "target_price": round(mx * 0.9, 2) if mx else None,
            "min_warranty": mission.get("warranty_requirements"),
            "max_delivery_days": mission.get("deadline_days")}


async def _get_mission_vendor(db, mission_id, vendor_id, user):
    mission = await db.missions.find_one(
        {"id": mission_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    vendor = await db.vendors.find_one({"id": vendor_id, "mission_id": mission_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return mission, vendor


async def get_thread(db, mission_id, vendor_id, org, vendor_name=None):
    thread = await db.negotiation_threads.find_one(
        {"mission_id": mission_id, "vendor_id": vendor_id}, {"_id": 0})
    if thread:
        return thread
    thread = {
        "id": uuid.uuid4().hex, "mission_id": mission_id, "vendor_id": vendor_id,
        "vendor_name": vendor_name, "organization_id": org,
        "state": "INITIATE", "next_action": None, "current_offer": {}, "previous_offer": {},
        "events": [], "decision_summary": None, "approval_status": "in_progress",
        "created_at": _now(), "updated_at": _now(),
    }
    await db.negotiation_threads.insert_one(dict(thread))
    return thread


def _merge_offer(current: dict, extracted: dict) -> dict:
    merged = dict(current or {})
    for k in _OFFER_KEYS:
        v = (extracted or {}).get(k)
        if v not in (None, "", []):
            merged[k] = v
    return merged


def _price_improvement(prev: dict, cur: dict):
    p, c = (prev or {}).get("unit_price"), (cur or {}).get("unit_price")
    try:
        if p and c and float(p) > 0:
            return round((float(p) - float(c)) / float(p) * 100, 1)
    except Exception:
        pass
    return None


async def converse(db, mission, vendor, org, channel, supplier_message, actor=None):
    thread = await get_thread(db, mission["id"], vendor["id"], org, vendor.get("name"))
    constraints = _constraints(mission)
    mem = await vendor_memory.get_memory(org, vendor.get("domain"))
    constraints["memory_note"] = vendor_memory.memory_note(mem)
    history = [{"role": e["role"], "text": e["text"]} for e in thread.get("events", [])]

    turn = await ai_service.engine_turn(
        mission, vendor, constraints, thread.get("state", "INITIATE"),
        thread.get("current_offer", {}), history, supplier_message,
        session_id=f"engine-{mission['id']}-{vendor['id']}")

    prev_offer = dict(thread.get("current_offer") or {})
    new_offer = _merge_offer(prev_offer, turn.get("extracted"))
    now = _now()
    events = thread.get("events", [])
    events.append({"id": uuid.uuid4().hex, "role": "supplier", "channel": channel,
                   "text": supplier_message, "at": now})
    events.append({"id": uuid.uuid4().hex, "role": "buyer_ai", "channel": channel,
                   "text": turn.get("reply", ""), "action": turn.get("next_action"), "at": now})

    # Authority check on any extracted price.
    mx = constraints.get("max_price")
    up = new_offer.get("unit_price")
    within_authority = True
    if mx is not None and up not in (None, ""):
        try:
            within_authority = float(up) <= float(mx)
        except Exception:
            within_authority = True

    new_state = turn.get("new_state")
    needs_approval = bool(turn.get("needs_human_approval")) and within_authority
    approval_status = thread.get("approval_status", "in_progress")
    if needs_approval:
        new_state = "AWAITING_HUMAN_APPROVAL"
        approval_status = "pending"
    if not within_authority:
        new_state = "NEGOTIATE"  # never advance to summary above authorized price

    update = {
        "state": new_state, "next_action": turn.get("next_action"),
        "previous_offer": prev_offer, "current_offer": new_offer,
        "events": events, "missing_info": turn.get("missing_info", []),
        "decision_summary": turn.get("decision_summary"),
        "within_authority": within_authority, "approval_status": approval_status,
        "max_authorized_price": mx, "updated_at": now,
    }
    await db.negotiation_threads.update_one(
        {"mission_id": mission["id"], "vendor_id": vendor["id"]}, {"$set": update})

    # Mirror into the offers collection so comparison/recommendation can see it.
    if up not in (None, ""):
        simulation = channel not in REAL_CHANNELS
        offer = {
            "id": uuid.uuid4().hex, "mission_id": mission["id"], "vendor_id": vendor["id"],
            "vendor_name": vendor.get("name"), "organization_id": org,
            "original_price": up, "negotiated_price": up, "quantity": mission.get("quantity") or 1,
            "taxes": new_offer.get("taxes"), "shipping": new_offer.get("shipping_cost"),
            "fees": new_offer.get("fees"), "currency": mission.get("currency"),
            "delivery_time": (f"{new_offer.get('delivery_days')} days"
                              if new_offer.get("delivery_days") else None),
            "warranty": new_offer.get("warranty"), "payment_terms": new_offer.get("payment_terms"),
            "reliability_score": vendor.get("reliability_score"),
            "source": "negotiation_engine", "channel": channel, "simulation": simulation,
            "within_authority": within_authority,
            "status": "OPEN" if within_authority else "OUT_OF_AUTHORITY",
            "max_authorized_price": mx, "created_at": now,
        }
        await db.offers.delete_many({"mission_id": mission["id"], "vendor_id": vendor["id"],
                                     "source": "negotiation_engine"})
        await db.offers.insert_one(offer)
        await vendor_memory.record_outcome(org, vendor, mission["id"], up,
                                            source=f"negotiation_{channel}")

    await audit.log_event(org, "negotiation_action", mission_id=mission["id"], actor=actor,
                          detail=f"[{channel}] {turn.get('next_action')} — {turn.get('decision_summary')}")

    thread = await db.negotiation_threads.find_one(
        {"mission_id": mission["id"], "vendor_id": vendor["id"]}, {"_id": 0})
    thread["reply"] = turn.get("reply", "")
    thread["price_improvement_pct"] = _price_improvement(prev_offer, new_offer)
    return thread


# --------------------------- endpoints --------------------------- #
@router.get("/{mission_id}/vendors/{vendor_id}/negotiation")
async def get_negotiation(mission_id: str, vendor_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    mission, vendor = await _get_mission_vendor(db, mission_id, vendor_id, user)
    thread = await get_thread(db, mission_id, vendor_id, user["organization_id"], vendor.get("name"))
    thread["price_improvement_pct"] = _price_improvement(
        thread.get("previous_offer"), thread.get("current_offer"))
    thread["constraints"] = _constraints(mission)
    return thread


class MessageBody(BaseModel):
    text: str
    channel: str = "sandbox"


@router.post("/{mission_id}/vendors/{vendor_id}/negotiation/message")
async def negotiation_message(mission_id: str, vendor_id: str, body: MessageBody,
                              user: dict = Depends(get_current_user)):
    db = get_db()
    mission, vendor = await _get_mission_vendor(db, mission_id, vendor_id, user)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Message required")
    return await converse(db, mission, vendor, user["organization_id"],
                          body.channel or "sandbox", body.text, actor=user.get("name"))


class DecisionBody(BaseModel):
    action: str  # approve | reject | negotiate_further


@router.post("/{mission_id}/vendors/{vendor_id}/negotiation/decision")
async def negotiation_decision(mission_id: str, vendor_id: str, body: DecisionBody,
                               user: dict = Depends(get_current_user)):
    if body.action not in ("approve", "reject", "negotiate_further"):
        raise HTTPException(status_code=400, detail="Invalid action")
    db = get_db()
    mission, vendor = await _get_mission_vendor(db, mission_id, vendor_id, user)
    mapping = {"approve": ("APPROVED", "approved"), "reject": ("REJECTED", "rejected"),
               "negotiate_further": ("NEGOTIATE_FURTHER", "in_progress")}
    state, status = mapping[body.action]
    await db.negotiation_threads.update_one(
        {"mission_id": mission_id, "vendor_id": vendor_id},
        {"$set": {"state": state, "approval_status": status, "updated_at": _now()}})
    await audit.log_event(user["organization_id"],
                          "human_approved" if body.action == "approve" else "negotiation_action",
                          mission_id=mission_id, actor=user.get("name"),
                          detail=f"Negotiation {body.action} for {vendor.get('name')}")
    # NOTE: approval here records intent only — it does NOT create a purchase/order.
    return await get_thread(db, mission_id, vendor_id, user["organization_id"], vendor.get("name"))
