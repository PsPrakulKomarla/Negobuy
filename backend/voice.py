"""Voice service — realtime conversational voice (OpenAI Realtime, browser WebRTC).
Telephony (outbound phone calls) uses a Twilio abstraction, reported separately.
Requires OPENAI_API_KEY. When absent, capability is reported as NOT_CONFIGURED."""
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from auth import get_current_user
import entitlements

router = APIRouter(prefix="/api/voice", tags=["voice"])

_realtime_registered = False


def voice_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def telephony_configured() -> bool:
    return bool(os.environ.get("TWILIO_ACCOUNT_SID")
                and os.environ.get("TWILIO_AUTH_TOKEN")
                and os.environ.get("TWILIO_PHONE_NUMBER"))


@router.get("/status")
async def voice_status(user: dict = Depends(get_current_user)):
    mins = await entitlements.voice_minutes_remaining(user)
    return {
        "configured": voice_configured(),
        "state": "READY" if voice_configured() else "NOT_CONFIGURED",
        "provider": "openai_realtime",
        "mode": "browser_webrtc",
        "telephony": {
            "configured": telephony_configured(),
            "state": "READY" if telephony_configured() else "NOT_CONFIGURED",
            "provider": "twilio",
            "requires": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
        },
        "requires": ["OPENAI_API_KEY"],
        "minutes": mins,
        "message": ("Realtime voice negotiation is ready (in-browser). "
                    "Outbound phone calls need Twilio telephony configuration."
                    if voice_configured()
                    else "Voice negotiation requires OPENAI_API_KEY."),
    }


class UsageBody(BaseModel):
    seconds: float


@router.post("/usage")
async def record_usage(body: UsageBody, user: dict = Depends(get_current_user)):
    minutes = max(0.0, body.seconds) / 60.0
    await entitlements.add_voice_usage(user["organization_id"], minutes)
    return await entitlements.voice_minutes_remaining(user)


def register_realtime(app):
    """Register OpenAI realtime WebRTC endpoints only when a key is present."""
    global _realtime_registered
    if _realtime_registered or not voice_configured():
        return
    try:
        from emergentintegrations.llm.openai import OpenAIChatRealtime
        chat = OpenAIChatRealtime(api_key=os.environ["OPENAI_API_KEY"])
        rt_router = APIRouter()
        OpenAIChatRealtime.register_openai_realtime_router(rt_router, chat)
        app.include_router(rt_router, prefix="/api/voice")
        _realtime_registered = True
        print("[voice] OpenAI Realtime router registered")
    except Exception as e:
        print(f"[voice] realtime registration failed: {e}")
