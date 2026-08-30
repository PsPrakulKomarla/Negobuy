"""WhatsApp Cloud API provider (architecture-ready). Reuses whatsapp.py sending when configured."""
import os
import logging

from .base_provider import CommunicationProvider

log = logging.getLogger("whatsapp_provider")


class WhatsAppProvider(CommunicationProvider):
    channel = "whatsapp"

    def is_configured(self) -> bool:
        return bool(os.environ.get("WHATSAPP_ACCESS_TOKEN")
                    and os.environ.get("WHATSAPP_PHONE_NUMBER_ID"))

    async def send_message(self, recipient: str, text: str) -> dict:
        if not self.is_configured():
            return {"ok": False, "status": "NOT_CONFIGURED", "provider_message_id": None,
                    "error": "WhatsApp Cloud API not configured"}
        try:
            import whatsapp as wa
            res = await wa._send_whatsapp(recipient, text)
            return {"ok": bool(res.get("ok")),
                    "status": "SENT" if res.get("ok") else "FAILED",
                    "provider_message_id": res.get("message_id"), "error": res.get("error")}
        except Exception as e:
            log.error("whatsapp send error: %s", type(e).__name__)
            return {"ok": False, "status": "FAILED", "provider_message_id": None,
                    "error": type(e).__name__}

    def validate_webhook(self, headers: dict, params: dict, body: dict) -> bool:
        return params.get("hub.verify_token") == os.environ.get("WHATSAPP_VERIFY_TOKEN") \
            if params.get("hub.verify_token") else True

    def normalize_message(self, payload: dict) -> dict | None:
        try:
            v = payload["entry"][0]["changes"][0]["value"]
            m = v["messages"][0]
            return {"event_id": f"wa-{m['id']}", "sender": m["from"],
                    "text": (m.get("text") or {}).get("body", ""),
                    "sender_name": ((v.get("contacts") or [{}])[0].get("profile") or {}).get("name",
                                                                                             m["from"]),
                    "is_echo": False}
        except Exception:
            return None
