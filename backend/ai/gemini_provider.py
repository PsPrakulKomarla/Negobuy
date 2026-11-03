"""Google Gemini provider — official google-genai SDK, own GEMINI_API_KEY (AQ. format)."""
import os
import logging
from .base_provider import AIProvider, CONFIGURED, NOT_CONFIGURED, INVALID_CONFIGURATION

log = logging.getLogger("ai.gemini")


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self):
        self._key = os.environ.get("GEMINI_API_KEY")
        self._model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self._key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            from google import genai
            self._client = genai.Client(api_key=self._key)
        return self._client

    def check_provider_status(self) -> str:
        if not self._key:
            return NOT_CONFIGURED
        if not self._key.startswith(("AQ.", "AIza")):
            return INVALID_CONFIGURATION
        return CONFIGURED

    async def generate_response(self, system: str, prompt: str, session_id: str | None = None) -> str:
        from google.genai import types
        client = self._get_client()
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        resp = await client.aio.models.generate_content(
            model=self._model, contents=prompt, config=config)
        return resp.text or ""
