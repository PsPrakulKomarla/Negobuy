"""Abstract communication provider. The negotiation engine talks ONLY to this interface,
never to Telegram/WhatsApp/Instagram APIs directly."""
from __future__ import annotations
from abc import ABC, abstractmethod


class CommunicationProvider(ABC):
    channel: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """True only when real credentials are present (never fake)."""

    def status(self) -> dict:
        return {"channel": self.channel,
                "state": "READY" if self.is_configured() else "NOT_CONFIGURED"}

    @abstractmethod
    async def send_message(self, recipient: str, text: str) -> dict:
        """Return {ok, provider_message_id, status, error?}. Must NOT fake success."""

    @abstractmethod
    def validate_webhook(self, headers: dict, params: dict, body: dict) -> bool:
        """Verify the inbound request is genuinely from the provider."""

    @abstractmethod
    def normalize_message(self, payload: dict) -> dict | None:
        """Return {event_id, sender, text, sender_name, is_echo} or None if not a user message."""

    def format_response(self, text: str) -> str:
        return text

    async def get_delivery_status(self, provider_message_id: str) -> str:
        return "unknown"
