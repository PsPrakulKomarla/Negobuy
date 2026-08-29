"""Vendor email outreach endpoints — AI compose/parse + SendGrid send, threaded per vendor."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db import get_db
from auth import get_current_user
import email_service
import vendor_memory
import orchestrator

router = APIRouter(prefix="/api/missions", tags=["outreach"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _mission(mission_id, user):
    m = await get_db().missions.find_one(
        {"id": mission_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found")
    return m


async def _vendor(mission_id, vendor_id):
    v = await get_db().vendors.find_one({"id": vendor_id, "mission_id": mission_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return v


async def _thread(mission_id, vendor_id):
    return await get_db().outreach_threads.find_one(
        {"mission_id": mission_id, "vendor_id": vendor_id}, {"_id": 0})


async def _append(mission_id, vendor_id, vendor, org_id, message):
    db = get_db()
    existing = await db.outreach_threads.find_one({"mission_id": mission_id, "vendor_id": vendor_id})
    if not existing:
        await db.outreach_threads.insert_one({
            "id": uuid.uuid4().hex, "mission_id": mission_id, "vendor_id": vendor_id,
            "vendor_name": vendor.get("name"), "organization_id": org_id,
            "messages": [message], "created_at": _now(), "updated_at": _now()})
    else:
        await db.outreach_threads.update_one(
            {"_id": existing["_id"]},
            {"$push": {"messages": message}, "$set": {"updated_at": _now()}})


class ComposeBody(BaseModel):
    tone: str | None = "professional"
    custom_instructions: str | None = None
    follow_up: bool = False


@router.post("/{mission_id}/vendors/{vendor_id}/outreach/strategy")
async def strategy(mission_id: str, vendor_id: str, user: dict = Depends(get_current_user)):
    m = await _mission(mission_id, user)
    v = await _vendor(mission_id, vendor_id)
    return await email_service.outreach_strategy(m, v, f"strat-{mission_id}-{vendor_id}")


@router.post("/{mission_id}/vendors/{vendor_id}/outreach/contact")
async def contact(mission_id: str, vendor_id: str, user: dict = Depends(get_current_user)):
    await _mission(mission_id, user)
    v = await _vendor(mission_id, vendor_id)
    result = await email_service.suggest_contact(v, f"contact-{vendor_id}")
    if v.get("contact_emails"):
        result["found_emails"] = v["contact_emails"]
    return result


@router.post("/{mission_id}/vendors/{vendor_id}/outreach/compose")
async def compose(mission_id: str, vendor_id: str, body: ComposeBody,
                  user: dict = Depends(get_current_user)):
    m = await _mission(mission_id, user)
    v = await _vendor(mission_id, vendor_id)
    thread = await _thread(mission_id, vendor_id)
    messages = (thread or {}).get("messages", [])
    return await email_service.compose_outreach(
        m, v, body.tone, body.custom_instructions, messages, body.follow_up,
        f"compose-{mission_id}-{vendor_id}")


class SendBody(BaseModel):
    to_email: str
    subject: str
    body_text: str
    body_html: str | None = None


@router.post("/{mission_id}/vendors/{vendor_id}/outreach/send")
async def send(mission_id: str, vendor_id: str, body: SendBody,
               user: dict = Depends(get_current_user)):
    m = await _mission(mission_id, user)
    v = await _vendor(mission_id, vendor_id)
    html = body.body_html or ("<p>" + (body.body_text or "").replace("\n", "<br>") + "</p>")
    result = email_service.send_email(body.to_email, body.subject, html, body.body_text)
    await _append(mission_id, vendor_id, v, user["organization_id"], {
        "id": uuid.uuid4().hex, "direction": "outbound", "to": body.to_email,
        "subject": body.subject, "body_text": body.body_text,
        "delivered": result.get("ok", False), "delivery": result, "at": _now()})
    if m.get("status") in ("REQUIREMENT_REVIEW", "COMPARING", "VERIFYING"):
        await orchestrator.set_status(mission_id, "CONTACTING")
    await orchestrator.log_action(
        mission_id, "Outreach Agent",
        f"Outreach email {'sent to' if result.get('ok') else 'attempted to'} {v.get('name')}",
        body.subject if result.get("ok") else f"Delivery failed: {result.get('error') or result.get('detail')}")
    return {"result": result, "message": (
        "Email sent." if result.get("ok")
        else "Email could not be sent — check that your SendGrid sender is verified.")}


class ReplyBody(BaseModel):
    subject: str | None = None
    body: str
    from_email: str | None = None


@router.post("/{mission_id}/vendors/{vendor_id}/outreach/reply")
async def reply(mission_id: str, vendor_id: str, body: ReplyBody,
                user: dict = Depends(get_current_user)):
    m = await _mission(mission_id, user)
    v = await _vendor(mission_id, vendor_id)
    parsed = await email_service.parse_reply(m, body.subject, body.body, f"parse-{mission_id}-{vendor_id}")
    await _append(mission_id, vendor_id, v, user["organization_id"], {
        "id": uuid.uuid4().hex, "direction": "inbound", "from": body.from_email,
        "subject": body.subject, "body_text": body.body, "parsed": parsed, "at": _now()})
    await orchestrator.log_action(mission_id, "Outreach Agent",
                                  f"Vendor reply parsed from {v.get('name')}",
                                  f"Extracted price {parsed.get('price_per_unit')} "
                                  f"(confidence {parsed.get('confidence')})")
    return {"parsed": parsed}


class ApplyOfferBody(BaseModel):
    price_per_unit: float
    lead_time_days: int | None = None
    payment_terms: str | None = None
    shipping_terms: str | None = None
    warranty: str | None = None


@router.post("/{mission_id}/vendors/{vendor_id}/outreach/apply-offer")
async def apply_offer(mission_id: str, vendor_id: str, body: ApplyOfferBody,
                      user: dict = Depends(get_current_user)):
    m = await _mission(mission_id, user)
    v = await _vendor(mission_id, vendor_id)
    db = get_db()
    qty = m.get("quantity") or 1
    offer = {
        "id": uuid.uuid4().hex, "mission_id": mission_id, "vendor_id": vendor_id,
        "vendor_name": v["name"], "organization_id": user["organization_id"],
        "original_price": body.price_per_unit, "negotiated_price": body.price_per_unit,
        "quantity": qty, "taxes": None, "shipping": None, "fees": None,
        "currency": m.get("currency"),
        "delivery_time": f"{body.lead_time_days} days" if body.lead_time_days else None,
        "warranty": body.warranty, "payment_terms": body.payment_terms,
        "shipping_terms": body.shipping_terms,
        "reliability_score": v.get("reliability_score"),
        "source": "vendor_email", "simulation": False, "status": "OPEN", "created_at": _now(),
    }
    await db.offers.delete_many({"mission_id": mission_id, "vendor_id": vendor_id})
    await db.offers.insert_one(dict(offer))
    await vendor_memory.record_outcome(user["organization_id"], v, mission_id,
                                        body.price_per_unit, source="email_quote")
    await orchestrator.log_action(mission_id, "Outreach Agent",
                                  f"Real offer captured from {v.get('name')}",
                                  f"{m.get('currency')} {body.price_per_unit}/unit from vendor email")
    offer.pop("_id", None)
    return offer


@router.get("/{mission_id}/vendors/{vendor_id}/outreach")
async def get_thread(mission_id: str, vendor_id: str, user: dict = Depends(get_current_user)):
    await _mission(mission_id, user)
    return await _thread(mission_id, vendor_id) or {"messages": []}


@router.post("/{mission_id}/vendors/{vendor_id}/outreach/summary")
async def summary(mission_id: str, vendor_id: str, user: dict = Depends(get_current_user)):
    await _mission(mission_id, user)
    thread = await _thread(mission_id, vendor_id)
    messages = (thread or {}).get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="No conversation to summarize yet.")
    return await email_service.thread_summary(messages, f"summary-{mission_id}-{vendor_id}")
