"""Exotel telephony provider + voice-session endpoints for NegoBuy.

Design rules enforced here:
- Credentials are read ONLY from env and never returned to any client.
- The backend is the sole source of truth for negotiation authority (max/target price).
  The voice agent receives authority as READ-ONLY context and can never change it.
- No endpoint in this module creates an offer, order, approval or purchase.
- Webhooks are validated with a shared secret (Exotel has no HMAC signing) and are
  idempotent on CallSid.

Verified against Exotel Voice v1 docs (Calls/connect + Passthru/StatusCallback), June 2026.
"""
import os
import uuid
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from db import get_db
from auth import get_current_user
import audit

log = logging.getLogger("exotel")
router = APIRouter(prefix="/api/voice/exotel", tags=["exotel"])

REQUIRED_VARS = ["EXOTEL_ACCOUNT_SID", "EXOTEL_API_KEY", "EXOTEL_API_TOKEN", "EXOTEL_SUBDOMAIN"]


# --------------------------------------------------------------------------- #
# Provider abstraction (swap this module out to change telephony provider).
# --------------------------------------------------------------------------- #
def _now():
    return datetime.now(timezone.utc).isoformat()


def is_configured() -> bool:
    return all(os.environ.get(v) for v in REQUIRED_VARS)


def caller_id() -> str | None:
    return os.environ.get("EXOTEL_CALLER_ID")


def config_status() -> dict:
    """Honest configuration status — never includes secret values."""
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if not os.environ.get("EXOTEL_CALLER_ID"):
        missing.append("EXOTEL_CALLER_ID")
    configured = len(missing) == 0
    return {
        "provider": "exotel",
        "configured": configured,
        "state": "READY" if configured else "NOT_CONFIGURED",
        "subdomain": os.environ.get("EXOTEL_SUBDOMAIN"),  # host only, not a secret
        "account_configured": bool(os.environ.get("EXOTEL_ACCOUNT_SID")),
        "caller_id_configured": bool(os.environ.get("EXOTEL_CALLER_ID")),
        "webhook_secured": bool(os.environ.get("EXOTEL_WEBHOOK_TOKEN")),
        "missing": missing,
        "message": ("Exotel voice calling is ready." if configured else
                    "Exotel needs " + ", ".join(missing) + " to place calls."),
    }


async def place_outbound_call(to_number: str, status_callback_url: str,
                              custom_field: str, record: bool = True) -> dict:
    """Initiate an Exotel connect call. Returns a sanitized result (no credentials)."""
    sid = os.environ["EXOTEL_ACCOUNT_SID"]
    key = os.environ["EXOTEL_API_KEY"]
    token = os.environ["EXOTEL_API_TOKEN"]
    sub = os.environ["EXOTEL_SUBDOMAIN"]
    url = f"https://{sub}/v1/Accounts/{sid}/Calls/connect.json"

    data = {
        "To": to_number,
        "CallerId": caller_id(),
        "CallType": "trans",
        "StatusCallback": status_callback_url,
        "StatusCallbackEvents[0]": "terminal",
        "CustomField": custom_field,
        "Record": "true" if record else "false",
    }
    # Route the answered call into a NegoBuy voice-bot flow / stream when configured.
    app_id = os.environ.get("EXOTEL_APP_ID")
    agent = os.environ.get("EXOTEL_AGENT_NUMBER")
    if app_id:
        data["Url"] = f"http://my.exotel.com/{sid}/exoml/start_voice/{app_id}"
    elif agent:
        data["From"] = agent
    stream = os.environ.get("EXOTEL_STREAM_URL")
    if stream:
        data["StreamUrl"] = stream
        data["StreamBegin"] = "at_Leg2Connect"

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(url, data=data, auth=(key, token))
    except Exception as e:
        log.error("Exotel call transport error for mission call: %s", type(e).__name__)
        return {"ok": False, "error": "provider_unreachable", "status_code": None,
                "provider_call_sid": None}

    call_sid = None
    parsed = None
    node = {}
    try:
        parsed = resp.json()
        # Exotel connect.json shapes: {"Call": {...}} or {"RestResponse": {...}}
        node = parsed.get("Call") or (parsed.get("RestResponse") or {}).get("Call") or {}
        call_sid = node.get("Sid") or node.get("CallSid")
    except Exception:
        parsed = {"raw": resp.text[:300]}

    ok = resp.status_code < 300
    # Never log tokens/keys — only non-sensitive identifiers.
    log.info("Exotel call accepted=%s http=%s call_sid=%s", ok, resp.status_code, call_sid)
    return {"ok": ok, "status_code": resp.status_code, "provider_call_sid": call_sid,
            "provider_response": (node if ok else parsed)}


# --------------------------------------------------------------------------- #
# Request helpers
# --------------------------------------------------------------------------- #
async def _merged_params(request: Request) -> dict:
    params: dict = {}
    try:
        form = await request.form()
        params.update({k: str(v) for k, v in form.items()})
    except Exception:
        pass
    params.update({k: v for k, v in request.query_params.items()})
    return params


def _check_webhook_token(params: dict):
    expected = os.environ.get("EXOTEL_WEBHOOK_TOKEN")
    if expected:
        if params.get("token") != expected:
            raise HTTPException(status_code=401, detail="Invalid webhook token")
    elif is_configured():
        # Exotel is live but no shared secret set — refuse unauthenticated webhooks.
        raise HTTPException(status_code=401, detail="Webhook secret not configured")


def _authority(mission: dict) -> dict:
    """Authority limits are computed by the backend ONLY — the source of truth."""
    qty = mission.get("quantity") or 1
    budget = mission.get("budget")
    max_price = round(budget / qty, 2) if (budget and qty) else None
    target = round(max_price * 0.9, 2) if max_price else None
    return {"currency": mission.get("currency"), "max_price_per_unit": max_price,
            "target_price_per_unit": target, "quantity": qty,
            "max_delivery_days": mission.get("deadline_days"),
            "min_warranty": mission.get("warranty_requirements")}


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/status")
async def exotel_status(user: dict = Depends(get_current_user)):
    return config_status()


class CallBody(BaseModel):
    mission_id: str
    vendor_id: str
    to_number: str | None = None


@router.post("/call")
async def start_call(body: CallBody, user: dict = Depends(get_current_user)):
    db = get_db()
    mission = await db.missions.find_one(
        {"id": body.mission_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    vendor = await db.vendors.find_one(
        {"id": body.vendor_id, "mission_id": body.mission_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    status = config_status()
    to_number = body.to_number or (vendor.get("contact_phones") or [None])[0]

    session_ref = uuid.uuid4().hex
    authority = _authority(mission)
    session_doc = {
        "id": uuid.uuid4().hex, "session_ref": session_ref, "provider": "exotel",
        "mission_id": body.mission_id, "vendor_id": body.vendor_id,
        "vendor_name": vendor.get("name"), "organization_id": user["organization_id"],
        "to": to_number, "authority": authority, "status": "initiating",
        "call_sid": None, "created_at": _now(),
    }

    if not status["configured"]:
        session_doc["status"] = "NOT_CONFIGURED"
        await db.voice_sessions.insert_one(dict(session_doc))
        await audit.log_event(user["organization_id"], "call_stub_recorded",
                              mission_id=body.mission_id, actor=user.get("name"),
                              detail=f"Exotel call requested — NOT_CONFIGURED ({', '.join(status['missing'])})")
        return {"status": "NOT_CONFIGURED", "provider": "exotel",
                "missing": status["missing"], "message": status["message"],
                "session_ref": session_ref}

    if not to_number:
        raise HTTPException(status_code=400, detail="No vendor phone number on record")

    base = os.environ.get("PUBLIC_BASE_URL", "")
    tok = os.environ.get("EXOTEL_WEBHOOK_TOKEN", "")
    status_cb = f"{base}/api/voice/exotel/session-end?token={tok}"

    result = await place_outbound_call(to_number, status_cb, custom_field=session_ref)
    session_doc["call_sid"] = result.get("provider_call_sid")
    session_doc["status"] = "calling" if result.get("ok") else "failed"
    await db.voice_sessions.insert_one(dict(session_doc))
    await db.calls.insert_one({
        "id": uuid.uuid4().hex, "provider": "exotel", "session_ref": session_ref,
        "mission_id": body.mission_id, "vendor_id": body.vendor_id,
        "organization_id": user["organization_id"], "to": to_number,
        "call_sid": result.get("provider_call_sid"), "status": session_doc["status"],
        "created_at": _now()})
    await audit.log_event(user["organization_id"], "call_started", mission_id=body.mission_id,
                          actor=user.get("name"),
                          detail=f"Exotel call to {vendor.get('name')} — {session_doc['status']}")
    # Response deliberately excludes all credentials.
    return {"status": session_doc["status"], "provider": "exotel",
            "session_ref": session_ref, "provider_call_sid": result.get("provider_call_sid"),
            "accepted": result.get("ok"), "http_status": result.get("status_code")}


@router.post("/session-start")
async def session_start(request: Request):
    """Exotel Passthru webhook. Returns READ-ONLY negotiation context for the voice agent.
    Never returns secrets or unrelated DB data, and cannot mutate authority."""
    params = await _merged_params(request)
    _check_webhook_token(params)
    db = get_db()
    session_ref = params.get("CustomField") or params.get("session_ref")
    call_sid = params.get("CallSid")
    query = {"session_ref": session_ref} if session_ref else ({"call_sid": call_sid} if call_sid else None)
    if not query:
        raise HTTPException(status_code=400, detail="Missing CustomField/CallSid")
    session = await db.voice_sessions.find_one(query, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Unknown voice session")
    if call_sid and not session.get("call_sid"):
        await db.voice_sessions.update_one({"session_ref": session["session_ref"]},
                                           {"$set": {"call_sid": call_sid, "status": "connected"}})
        await db.calls.update_one({"session_ref": session["session_ref"]},
                                  {"$set": {"call_sid": call_sid, "status": "connected"}})
    mission = await db.missions.find_one({"id": session["mission_id"]}, {"_id": 0}) or {}
    authority = session.get("authority") or _authority(mission)
    # Only the dynamic info the agent needs. Authority is read-only context.
    return {
        "session_ref": session["session_ref"],
        "vendor_name": session.get("vendor_name"),
        "mission": {"title": mission.get("title"), "quantity": mission.get("quantity"),
                    "delivery_location": mission.get("delivery_location"),
                    "deadline_days": mission.get("deadline_days")},
        "authority": authority,
        "questions": ["price per unit", "minimum order quantity", "lead time",
                      "warranty", "payment terms", "shipping terms"],
        "rules": ("Negotiate toward the target price and never exceed the maximum authorized "
                  "price. You may not commit, approve, or place any order. A human approves "
                  "all purchases."),
    }


@router.post("/session-end")
async def session_end(request: Request):
    """Exotel StatusCallback webhook. Persists call outcome. Never creates a purchase."""
    params = await _merged_params(request)
    _check_webhook_token(params)
    db = get_db()
    session_ref = params.get("CustomField") or params.get("session_ref")
    call_sid = params.get("CallSid")
    query = {"session_ref": session_ref} if session_ref else ({"call_sid": call_sid} if call_sid else None)
    if not query:
        raise HTTPException(status_code=400, detail="Missing CustomField/CallSid")
    session = await db.voice_sessions.find_one(query)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown voice session")

    # Idempotency: ignore duplicate terminal callbacks for the same CallSid.
    if session.get("status") in ("completed", "failed", "no-answer", "busy") and \
            session.get("terminal_recorded"):
        return {"status": "duplicate"}

    call_status = params.get("CallStatus") or params.get("DialCallStatus") or "completed"
    duration = params.get("ConversationDuration") or params.get("DialCallDuration") \
        or params.get("OnCallDuration") or params.get("Duration")
    recording = params.get("RecordingUrl")
    # Optional agent-reported offer fields — STORED ONLY, never auto-applied.
    reported_offer = {k: params.get(k) for k in
                      ("price_per_unit", "moq", "lead_time_days", "payment_terms",
                       "shipping_terms", "transcript") if params.get(k) is not None}

    update = {"status": call_status, "duration": duration, "recording_url": recording,
              "reported_offer": reported_offer or None, "terminal_recorded": True,
              "ended_at": _now()}
    await db.voice_sessions.update_one({"session_ref": session["session_ref"]}, {"$set": update})
    await db.calls.update_one({"session_ref": session["session_ref"]},
                              {"$set": {"status": call_status, "duration": duration,
                                        "recording_url": recording, "ended_at": _now()}})
    await audit.log_event(session["organization_id"], "call_ended",
                          mission_id=session["mission_id"],
                          detail=f"Exotel call {call_status}"
                                 + (f", {duration}s" if duration else ""))
    return {"status": "recorded", "call_status": call_status}
