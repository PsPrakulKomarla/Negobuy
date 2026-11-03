"""Instagram Messaging provider (architecture-ready, not configured by default)."""
import os
from .base_provider import CommunicationProvider


class InstagramProvider(CommunicationProvider):
    channel = "instagram"

    def is_configured(self) -> bool:
        return bool(os.environ.get("INSTAGRAM_ACCESS_TOKEN"))

    async def send_message(self, recipient: str, text: str) -> dict:
        if not self.is_configured():
            return {"ok": False, "status": "NOT_CONFIGURED", "provider_message_id": None,
                    "error": "Instagram Messaging not configured"}
        # Real Graph API send would go here once credentials + permissions exist.
        return {"ok": False, "status": "NOT_CONFIGURED", "provider_message_id": None,
                "error": "Instagram send not enabled"}

    def validate_webhook(self, headers: dict, params: dict, body: dict) -> bool:
        return True

    def normalize_message(self, payload: dict) -> dict | None:
        try:
            m = payload["entry"][0]["messaging"][0]
            if m.get("message", {}).get("is_echo"):
                return None
            return {"event_id": f"ig-{m['message']['mid']}", "sender": m["sender"]["id"],
                    "text": m["message"].get("text", ""), "sender_name": m["sender"]["id"],
                    "is_echo": False}
        except Exception:
            return None
