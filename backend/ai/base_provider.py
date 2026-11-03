"""Common AI provider interface. The negotiation engine / ai_service depend on THIS,
not on any specific vendor SDK. Concrete providers implement generate_response() and
check_provider_status(); everything else is built on top."""
import json
import re
from abc import ABC, abstractmethod

CONFIGURED = "CONFIGURED"
NOT_CONFIGURED = "NOT_CONFIGURED"
INVALID_CONFIGURATION = "INVALID_CONFIGURATION"


def extract_json(text: str):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


class AIProvider(ABC):
    name = "base"

    @abstractmethod
    async def generate_response(self, system: str, prompt: str, session_id: str | None = None) -> str:
        """Return raw model text for a system+user prompt."""

    @abstractmethod
    def check_provider_status(self) -> str:
        """CONFIGURED | NOT_CONFIGURED | INVALID_CONFIGURATION (no network call)."""

    # ----- generic helpers built on generate_response (common interface) ----- #
    async def generate_structured_output(self, system: str, prompt: str,
                                         session_id: str | None = None) -> dict:
        raw = await self.generate_response(system, prompt, session_id)
        return extract_json(raw)

    async def summarize_conversation(self, transcript: str, session_id: str | None = None) -> dict:
        sys = ("Summarize this negotiation conversation for a buyer. Return ONLY JSON: "
               '{"summary": string, "key_points": [string], "latest_price": number|null}')
        return await self.generate_structured_output(sys, transcript, session_id)

    async def extract_offer_information(self, message: str, session_id: str | None = None) -> dict:
        sys = ("Extract commercial terms from this supplier message. Never invent values; use null. "
               'Return ONLY JSON: {"unit_price": number|null, "quantity": number|null, '
               '"delivery_days": number|null, "warranty": string|null, "payment_terms": string|null, '
               '"shipping": string|null, "taxes": string|null}')
        return await self.generate_structured_output(sys, message, session_id)

    async def analyze_negotiation(self, context: str, session_id: str | None = None) -> dict:
        sys = ("Analyze this negotiation for the buyer. Do not fabricate. Return ONLY JSON: "
               '{"assessment": string, "risks": [string], "recommended_next_action": string}')
        return await self.generate_structured_output(sys, context, session_id)
