"""Direct Business Negotiation — dashboard capability to negotiate with a specific business.

REUSES (does not duplicate):
  - ai_service.extract_requirement  (Requirement Intelligence agent)
  - ai_service.negotiation_plan     (plan built from the shared persona)
  - ai_service.analyze_call         (unified call+chat analysis)
  - negotiation_engine (get_thread / converse / _constraints)  — ONE shared thread
  - call_center (config + approve + simulation)  — the phone-call lifecycle
  - whatsapp (_send_whatsapp / wa_configured)     — WhatsApp channel + webhooks
  - exotel_service / voice              — provider status (never faked)
  - audit.log_event                     — unified honest timeline

Adds: a single "direct negotiation" entry point that creates a mission + business supplier,
prepares a negotiation plan for human review, and a controlled WhatsApp fallback +
unified timeline + final report. Phone and WhatsApp share the SAME negotiation memory.
Nothing here commits a purchase — human approval is always required.
"""
import os
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from auth import get_current_user
import audit
import ai_service
import exotel_service
import vendor_memory
import negotiation_engine
import whatsapp as wa
from voice import voice_configured

log = logging.getLogger("direct_negotiation")
router = APIRouter(prefix="/api/direct-negotiation", tags=["direct-negotiation"])

# Provider statuses that make a WhatsApp fallback appropriate (provider-confirmed).
FALLBACK_STATUSES = {"no-answer", "busy", "failed", "unreachable", "canceled", "call_dropped"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _authority(target, mx, qty, days, warranty, currency):
    return {"currency": currency or "INR", "target_price_per_unit": target,
            "max_price_per_unit": mx, "quantity": qty or 1,
            "max_delivery_days": days, "min_warranty": warranty}


async def _mission(db, mission_id, user):
    m = await db.missions.find_one(
        {"id": mission_id, "organization_id": user["organization_id"],
         "source": "direct_negotiation"}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Direct negotiation not found")
    return m


async def _business(db, mission_id, org=None):
    q = {"mission_id": mission_id}
    if org:
        q["organization_id"] = org
    return await db.vendors.find_one(q, {"_id": 0})


# --------------------------------------------------------------------------- #
# 1. PREPARE — structure requirement + create mission/business + plan (NO call)
# --------------------------------------------------------------------------- #
class PrepareBody(BaseModel):
    business_name: str
    contact_name: str | None = None
    phone_number: str | None = None
    whatsapp_number: str | None = None
    business_description: str | None = None
    what_to_buy: str  # natural language of the requirement
    product: str | None = None
    quantity: int | None = None
    target_price: float | None = None
    min_price: float | None = None
    max_authorized_price: float | None = None
    currency: str | None = "INR"
    delivery_location: str | None = None
    delivery_deadline_days: int | None = None
    payment_preference: str | None = None
    warranty_requirements: str | None = None
    quality_requirements: str | None = None
    other_instructions: str | None = None


@router.post("/prepare")
async def prepare(body: PrepareBody, user: dict = Depends(get_current_user)):
    if not ai_service.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured")
    if body.target_price is not None and body.max_authorized_price is not None \
            and float(body.target_price) > float(body.max_authorized_price):
        raise HTTPException(status_code=400,
                            detail="Target price cannot exceed the maximum authorized price")
    db = get_db()
    org = user["organization_id"]

    # --- Requirement Intelligence (reused) ---
    req_text = (f"I want to buy from {body.business_name}. {body.what_to_buy}. "
                f"Product: {body.product or ''}. Quantity: {body.quantity or ''}. "
                f"Target price: {body.target_price or ''}. "
                f"Maximum authorized price: {body.max_authorized_price or ''} {body.currency or ''}. "
                f"Deliver to {body.delivery_location or ''} "
                f"within {body.delivery_deadline_days or ''} days. "
                f"Payment: {body.payment_preference or ''}. Warranty: {body.warranty_requirements or ''}. "
                f"Quality: {body.quality_requirements or ''}. Other: {body.other_instructions or ''}.")
    requirement = await ai_service.extract_requirement(req_text, f"direct-req-{user['id']}")

    qty = body.quantity or requirement.get("quantity")
    currency = body.currency or requirement.get("currency") or "INR"
    mission = {
        "id": uuid.uuid4().hex, "organization_id": org, "created_by": user["id"],
        "source": "direct_negotiation",
        "title": requirement.get("title") or f"{body.product or body.what_to_buy} — {body.business_name}",
        "description": body.what_to_buy,
        "category": requirement.get("category"),
        "product": body.product or requirement.get("product"),
        "quantity": qty, "unit": requirement.get("unit"),
        "budget": (body.max_authorized_price * qty) if (body.max_authorized_price and qty) else None,
        "currency": currency,
        "delivery_location": body.delivery_location or requirement.get("delivery_location"),
        "deadline_days": body.delivery_deadline_days or requirement.get("deadline_days"),
        "warranty_requirements": body.warranty_requirements or requirement.get("warranty_requirements"),
        "payment_requirements": body.payment_preference,
        "specifications": requirement.get("specifications") or [],
        "special_instructions": body.other_instructions,
        "status": "REQUIREMENT_REVIEW", "created_at": _now(), "updated_at": _now(),
    }
    await db.missions.insert_one(dict(mission))

    phone = exotel_service._normalize_number(body.phone_number)
    wapp = exotel_service._normalize_number(body.whatsapp_number or body.phone_number)
    business = {
        "id": uuid.uuid4().hex, "mission_id": mission["id"], "organization_id": org,
        "name": body.business_name, "contact_name": body.contact_name,
        "description": body.business_description,
        "domain": None, "website": None, "location": body.delivery_location,
        "verification_status": "UNVERIFIED", "weighted_score": 0,
        "contact_phones": [p for p in [phone] if p],
        "whatsapp_number": wapp, "source": "direct_negotiation", "created_at": _now(),
    }
    await db.vendors.insert_one(dict(business))

    authority = _authority(body.target_price, body.max_authorized_price, qty,
                           mission["deadline_days"], mission["warranty_requirements"], currency)
    # Shared negotiation thread (org -> mission -> supplier).
    await negotiation_engine.get_thread(db, mission["id"], business["id"], org, business["name"])

    plan = await ai_service.negotiation_plan(mission, business, authority,
                                             f"direct-plan-{mission['id']}")

    call_status = await exotel_service.live_status()
    providers = {
        "call": {"state": call_status.get("state"), "provider": "exotel"},
        "recording": {"state": "RECORDING_AVAILABLE" if call_status.get("state") == "READY"
                      else "RECORDING_NOT_SUPPORTED"},
        "transcript": {"state": "READY" if voice_configured() else "NOT_CONFIGURED",
                       "provider": "openai_realtime"},
        "whatsapp_fallback": {"state": "READY" if wa.wa_configured() else "NOT_CONFIGURED",
                              "provider": "meta_cloud_api"},
    }

    await audit.log_event(org, "mission_created", mission_id=mission["id"],
                          actor=user.get("name"), detail=f"Direct negotiation: {mission['title']}")
    await audit.log_event(org, "negotiation_plan_created", mission_id=mission["id"],
                          actor=user.get("name"),
                          detail=f"Plan prepared for {business['name']}")

    business.pop("_id", None)
    mission.pop("_id", None)
    return {"mission_id": mission["id"], "vendor_id": business["id"],
            "mission": mission, "business": business, "requirement": requirement,
            "authority": authority, "plan": plan, "providers": providers,
            "phone_number": phone, "whatsapp_number": wapp}


# --------------------------------------------------------------------------- #
# 2. UNIFIED TIMELINE (from the honest audit stream + artifacts)
# --------------------------------------------------------------------------- #
EVENT_TITLES = {
    "mission_created": "Mission created", "negotiation_plan_created": "AI prepared negotiation plan",
    "call_configured": "Call configured", "call_approved": "User approved call",
    "call_started": "Call initiated", "call_ended": "Call ended",
    "message_sent": "WhatsApp message sent", "whatsapp_fallback": "WhatsApp fallback",
    "whatsapp_reply": "Business replied on WhatsApp", "negotiation_action": "AI negotiation action",
    "human_approved": "Human approval", "direct_decision": "User decision",
}


@router.get("/{mission_id}/timeline")
async def timeline(mission_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    await _mission(db, mission_id, user)
    logs = await db.audit_logs.find(
        {"organization_id": user["organization_id"], "mission_id": mission_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    items = [{"at": l["created_at"], "type": l["event_type"],
              "title": EVENT_TITLES.get(l["event_type"], l["event_type"].replace("_", " ").title()),
              "detail": l.get("detail"), "actor": l.get("actor")} for l in logs]
    return {"timeline": items}


# --------------------------------------------------------------------------- #
# 3. CONTROLLED WHATSAPP FALLBACK (one message; provider-confirmed no-answer)
# --------------------------------------------------------------------------- #
class FallbackBody(BaseModel):
    call_ref: str | None = None
    simulate: bool = True  # simulate delivery when WhatsApp is NOT_CONFIGURED


@router.post("/{mission_id}/fallback")
async def whatsapp_fallback(mission_id: str, body: FallbackBody,
                            user: dict = Depends(get_current_user)):
    db = get_db()
    mission = await _mission(db, mission_id, user)
    business = await _business(db, mission_id, user["organization_id"])
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Anti-spam: only one fallback follow-up per mission.
    existing = await db.messages.find_one(
        {"mission_id": mission_id, "kind": "fallback"}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="A WhatsApp fallback was already sent")

    # Verify the call actually reached a fallback-eligible status (never assume).
    if body.call_ref:
        call = await db.voice_calls.find_one({"session_ref": body.call_ref}, {"_id": 0})
        status = (call or {}).get("status", "")
        if status not in FALLBACK_STATUSES:
            raise HTTPException(status_code=400,
                                detail=f"Call status '{status}' is not a fallback-eligible no-answer")

    to = business.get("whatsapp_number") or (business.get("contact_phones") or [None])[0]
    if not to:
        raise HTTPException(status_code=400, detail="No WhatsApp number on record")

    product = mission.get("product") or mission.get("title")
    message = (f"Hello, this is NegoBuy's AI procurement assistant. I tried reaching you by phone "
               f"to discuss a potential purchase on behalf of a buyer. We'd like to understand your "
               f"pricing and availability for {product}. Please let me know when convenient and we "
               f"can continue here.")

    delivery = {"ok": False, "simulated": True, "state": "SIMULATED"}
    if wa.wa_configured():
        delivery = await wa._send_whatsapp(to, message)
        delivery["simulated"] = False
        delivery["state"] = "SENT" if delivery.get("ok") else "FAILED"
    elif not body.simulate:
        return {"status": "NOT_CONFIGURED", "provider": "meta_cloud_api",
                "message": "WhatsApp Cloud API is not configured — cannot send a real message."}

    msg = {"id": uuid.uuid4().hex, "channel": "whatsapp", "direction": "outbound",
           "kind": "fallback", "to": to, "text": message, "delivery": delivery,
           "mission_id": mission_id, "vendor_id": business["id"],
           "organization_id": user["organization_id"], "created_at": _now()}
    await db.messages.insert_one(dict(msg))
    # Shared memory: record the fallback in the negotiation thread.
    thread = await negotiation_engine.get_thread(db, mission_id, business["id"],
                                                 user["organization_id"], business["name"])
    events = thread.get("events", [])
    events.append({"id": uuid.uuid4().hex, "role": "buyer_ai", "channel": "whatsapp",
                   "text": message, "at": _now()})
    await db.negotiation_threads.update_one(
        {"mission_id": mission_id, "vendor_id": business["id"]},
        {"$set": {"events": events, "updated_at": _now()}})
    await audit.log_event(user["organization_id"], "whatsapp_fallback", mission_id=mission_id,
                          actor=user.get("name"),
                          detail=f"WhatsApp follow-up to {business['name']} "
                                 f"({'sent' if delivery.get('ok') else delivery.get('state')})")
    msg.pop("_id", None)
    return {"status": "sent", "delivery": delivery, "message": msg}


# --------------------------------------------------------------------------- #
# 4. WHATSAPP REPLY — routed through the SHARED negotiation brain (same thread)
# --------------------------------------------------------------------------- #
class ReplyBody(BaseModel):
    text: str
    simulate: bool = True


@router.post("/{mission_id}/whatsapp-reply")
async def whatsapp_reply(mission_id: str, body: ReplyBody,
                         user: dict = Depends(get_current_user)):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Message required")
    db = get_db()
    mission = await _mission(db, mission_id, user)
    business = await _business(db, mission_id, user["organization_id"])
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    to = business.get("whatsapp_number") or (business.get("contact_phones") or [None])[0]

    # store inbound
    await db.messages.insert_one({
        "id": uuid.uuid4().hex, "channel": "whatsapp", "direction": "inbound",
        "from": to, "text": body.text, "mission_id": mission_id, "vendor_id": business["id"],
        "organization_id": user["organization_id"], "created_at": _now()})
    await audit.log_event(user["organization_id"], "whatsapp_reply", mission_id=mission_id,
                          detail=f"{business['name']}: {body.text[:80]}")

    # Route through the SAME negotiation engine thread (shared memory: it can see the call).
    thread = await negotiation_engine.converse(
        db, mission, business, user["organization_id"], "whatsapp", body.text,
        actor=user.get("name"))
    reply_text = thread.get("reply", "")

    delivery = {"ok": False, "simulated": True, "state": "SIMULATED"}
    if wa.wa_configured() and to:
        delivery = await wa._send_whatsapp(to, reply_text)
    await db.messages.insert_one({
        "id": uuid.uuid4().hex, "channel": "whatsapp", "direction": "outbound",
        "to": to, "text": reply_text, "delivery": delivery, "mission_id": mission_id,
        "vendor_id": business["id"], "organization_id": user["organization_id"],
        "created_at": _now()})
    return {"reply": reply_text, "delivery": delivery,
            "state": thread.get("state"), "current_offer": thread.get("current_offer"),
            "approval_status": thread.get("approval_status"),
            "within_authority": thread.get("within_authority", True)}


# --------------------------------------------------------------------------- #
# 5. FINAL REPORT (combines phone transcript + WhatsApp into one analysis)
# --------------------------------------------------------------------------- #
@router.post("/{mission_id}/generate-report")
async def generate_report(mission_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    mission = await _mission(db, mission_id, user)
    business = await _business(db, mission_id, user["organization_id"])
    calls = await db.voice_calls.find({"mission_id": mission_id}, {"_id": 0}).sort(
        "created_at", 1).to_list(20)
    messages = await db.messages.find({"mission_id": mission_id}, {"_id": 0}).sort(
        "created_at", 1).to_list(200)

    combined = []
    for c in calls:
        for t in (c.get("transcript") or []):
            combined.append({"speaker": t.get("speaker"), "text": t.get("text"),
                             "timestamp": f"call {t.get('timestamp', '')}"})
    for m in messages:
        combined.append({"speaker": "AI" if m.get("direction") == "outbound" else "SUPPLIER",
                         "text": m.get("text"), "timestamp": "whatsapp"})
    if not combined:
        raise HTTPException(status_code=400,
                            detail="No conversation yet (run a call or exchange WhatsApp messages)")

    qty = mission.get("quantity")
    authority = _authority(None, None, qty, mission.get("deadline_days"),
                           mission.get("warranty_requirements"), mission.get("currency"))
    # pull frozen authority from any call if present
    if calls and calls[-1].get("authority"):
        authority = calls[-1]["authority"]
    objective = {"product": mission.get("product") or mission.get("title"), "quantity": qty,
                 "delivery_location": mission.get("delivery_location"),
                 "special_instructions": mission.get("special_instructions")}
    analysis = await ai_service.analyze_call(objective, authority, combined,
                                             f"direct-report-{mission_id}")
    await db.missions.update_one({"id": mission_id},
                                 {"$set": {"direct_report": analysis, "updated_at": _now()}})
    return analysis


# --------------------------------------------------------------------------- #
# 6. FULL VIEW — everything for the report screen (shared memory surfaced)
# --------------------------------------------------------------------------- #
@router.get("/{mission_id}")
async def full(mission_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    mission = await _mission(db, mission_id, user)
    business = await _business(db, mission_id, user["organization_id"])
    thread = await db.negotiation_threads.find_one(
        {"mission_id": mission_id, "vendor_id": (business or {}).get("id")}, {"_id": 0})
    calls = await db.voice_calls.find({"mission_id": mission_id}, {"_id": 0}).sort(
        "created_at", -1).to_list(20)
    messages = await db.messages.find({"mission_id": mission_id}, {"_id": 0}).sort(
        "created_at", 1).to_list(200)
    offers = await db.offers.find({"mission_id": mission_id}, {"_id": 0}).to_list(50)
    return {"mission": mission, "business": business, "thread": thread,
            "calls": calls, "messages": messages, "offers": offers,
            "report": mission.get("direct_report"), "decision": mission.get("direct_decision")}


# --------------------------------------------------------------------------- #
# 7. USER ACTIONS AFTER NEGOTIATION (never auto-purchase)
# --------------------------------------------------------------------------- #
class DecisionBody(BaseModel):
    action: str  # CONTINUE | COUNTEROFFER | REQUEST_HUMAN_REVIEW | APPROVE_NEXT | REJECT | END
    note: str | None = None


@router.post("/{mission_id}/decision")
async def decision(mission_id: str, body: DecisionBody, user: dict = Depends(get_current_user)):
    valid = {"CONTINUE", "COUNTEROFFER", "REQUEST_HUMAN_REVIEW", "APPROVE_NEXT", "REJECT", "END"}
    if body.action not in valid:
        raise HTTPException(status_code=400, detail="Invalid action")
    db = get_db()
    mission = await _mission(db, mission_id, user)
    dec = {"action": body.action, "note": body.note, "by": user.get("name"), "at": _now()}
    await db.missions.update_one({"id": mission_id},
                                 {"$set": {"direct_decision": dec, "updated_at": _now()}})
    await audit.log_event(user["organization_id"],
                          "human_approved" if body.action == "APPROVE_NEXT" else "direct_decision",
                          mission_id=mission_id, actor=user.get("name"),
                          detail=f"Direct negotiation decision: {body.action}"
                                 + (f" — {body.note}" if body.note else ""))
    # NOTE: APPROVE_NEXT records intent only — no order/purchase is created here.
    return {"ok": True, "decision": dec}


@router.get("")
async def list_direct(user: dict = Depends(get_current_user)):
    db = get_db()
    docs = await db.missions.find(
        {"organization_id": user["organization_id"], "source": "direct_negotiation"},
        {"_id": 0}).sort("created_at", -1).to_list(100)
    return docs
