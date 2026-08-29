"""Voice service — realtime conversational voice architecture (OpenAI Realtime).
Requires OPENAI_API_KEY. When absent, the capability is reported as NOT CONFIGURED.
This layer is intentionally separated from procurement business logic."""
import os
from fastapi import APIRouter, HTTPException, Depends
from auth import get_current_user

router = APIRouter(prefix="/api/voice", tags=["voice"])

_realtime_registered = False


def voice_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


@router.get("/status")
async def voice_status(user: dict = Depends(get_current_user)):
    return {
        "configured": voice_configured(),
        "provider": "openai_realtime",
        "requires": ["OPENAI_API_KEY"],
        "message": ("Realtime voice negotiation is ready." if voice_configured()
                    else "Voice negotiation requires an OpenAI Realtime API key. "
                         "Add OPENAI_API_KEY to enable live vendor calls."),
    }


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
    except Exception as e:
        print(f"[voice] realtime registration failed: {e}")
