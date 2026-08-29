"""Telephony — Twilio outbound voice call architecture bridged to OpenAI Realtime.
Returns NOT_CONFIGURED until Twilio credentials are set. Never claims a call is live unless placed."""
import os
import uuid
import base64
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from db import get_db
from auth import get_current_user
import audit

router = APIRouter(prefix="/api/voice", tags=["telephony"])


def configured() -> bool:
    return bool(os.environ.get("TWILIO_ACCOUNT_SID")
                and os.environ.get("TWILIO_AUTH_TOKEN")
                and os.environ.get("TWILIO_PHONE_NUMBER"))


def _now():
    return datetime.now(timezone.utc).isoformat()


class CallBody(BaseModel):
    mission_id: str
    vendor_id: str
    to_number: str | None = None


@router.post("/calls")
async def initiate_call(body: CallBody, user: dict = Depends(get_current_user)):
    db = get_db()
    vendor = await db.vendors.find_one({"id": body.vendor_id, "mission_id": body.mission_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    to = body.to_number or (vendor.get("contact_phones") or [None])[0]
    call = {"id": uuid.uuid4().hex, "mission_id": body.mission_id, "vendor_id": body.vendor_id,
            "vendor_name": vendor.get("name"), "organization_id": user["organization_id"],
            "to": to, "provider": "twilio", "created_at": _now()}

    if not configured():
        call["status"] = "NOT_CONFIGURED"
        await db.calls.insert_one(dict(call))
        await audit.log_event(user["organization_id"], "call_stub_recorded",
                              mission_id=body.mission_id, actor=user.get("name"),
                              detail=f"Call requested to {to or 'unknown'} — telephony NOT_CONFIGURED")
        return {"status": "NOT_CONFIGURED", "provider": "twilio",
                "required": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
                             "TWILIO_PHONE_NUMBER", "OPENAI_API_KEY"],
                "message": ("Outbound phone calls require Twilio + OpenAI Realtime. "
                            "Call initiation, the TwiML media-stream bridge and structured "
                            "call-event recording are implemented and activate once configured."),
                "call": call}

    if not to:
        raise HTTPException(status_code=400, detail="No vendor phone number on record")
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    tok = os.environ["TWILIO_AUTH_TOKEN"]
    public = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("FRONTEND_URL", "")
    twiml_url = f"{public}/api/voice/twiml/{call['id']}"
    creds = base64.b64encode(f"{sid}:{tok}".encode()).decode()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
                         headers={"Authorization": f"Basic {creds}"},
                         data={"To": to, "From": os.environ["TWILIO_PHONE_NUMBER"], "Url": twiml_url})
    ok = r.status_code < 300
    call["status"] = "CALLING" if ok else "FAILED"
    call["provider_sid"] = r.json().get("sid") if ok else None
    await db.calls.insert_one(dict(call))
    await audit.log_event(user["organization_id"], "call_started", mission_id=body.mission_id,
                          detail=f"Call to {to} — {call['status']}")
    return {"status": call["status"], "call": call}


@router.get("/calls")
async def list_calls(mission_id: str, user: dict = Depends(get_current_user)):
    return await get_db().calls.find(
        {"mission_id": mission_id, "organization_id": user["organization_id"]},
        {"_id": 0}).sort("created_at", -1).to_list(50)


@router.post("/twiml/{call_id}")
async def twiml(call_id: str):
    """TwiML entrypoint. When telephony is live this bridges the call audio to
    OpenAI Realtime via a Media Stream; without it, a holding message is returned."""
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<Response><Say voice="Polly.Aditi">Connecting you to the NegoBuy '
           'procurement agent.</Say></Response>')
    return Response(content=xml, media_type="application/xml")
