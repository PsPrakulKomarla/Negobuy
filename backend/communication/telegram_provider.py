"""Telegram Bot API provider."""
import os
import logging
import httpx

from .base_provider import CommunicationProvider

log = logging.getLogger("telegram_provider")


class TelegramProvider(CommunicationProvider):
    channel = "telegram"

    def _token(self):
        return os.environ.get("TELEGRAM_BOT_TOKEN")

    def is_configured(self) -> bool:
        return bool(self._token())

    async def send_message(self, recipient: str, text: str) -> dict:
        token = self._token()
        if not token:
            return {"ok": False, "status": "NOT_CONFIGURED", "provider_message_id": None,
                    "error": "TELEGRAM_BOT_TOKEN not set"}
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                 json={"chat_id": recipient, "text": text})
            j = r.json()
            if r.status_code == 200 and j.get("ok"):
                return {"ok": True, "status": "SENT",
                        "provider_message_id": str(j["result"]["message_id"])}
            return {"ok": False, "status": "FAILED", "provider_message_id": None,
                    "error": j.get("description", "send failed")}
        except Exception as e:
            log.error("telegram send error: %s", type(e).__name__)
            return {"ok": False, "status": "FAILED", "provider_message_id": None,
                    "error": type(e).__name__}

    def validate_webhook(self, headers: dict, params: dict, body: dict) -> bool:
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if not secret:
            return True  # no secret configured -> accept (dev/mock)
        got = headers.get("x-telegram-bot-api-secret-token") or params.get("secret")
        return got == secret

    def normalize_message(self, payload: dict) -> dict | None:
        # Ignore edited messages / non-message updates to avoid loops & duplicates.
        msg = payload.get("message")
        if not msg or "text" not in msg:
            return None
        frm = msg.get("from") or {}
        if frm.get("is_bot"):
            return None  # never react to bot/echo messages
        name = " ".join(x for x in [frm.get("first_name"), frm.get("last_name")] if x) \
            or frm.get("username") or str((msg.get("chat") or {}).get("id"))
        return {
            "event_id": f"tg-{payload.get('update_id')}",
            "sender": str((msg.get("chat") or {}).get("id")),
            "text": msg.get("text", ""),
            "sender_name": name,
            "is_echo": False,
        }
