"""xAI (Grok) provider — OpenAI-compatible REST endpoint, own XAI_API_KEY.
Pluggable/future: NOT_CONFIGURED until XAI_API_KEY is set. Never fakes a response."""
import os
import httpx
from .base_provider import AIProvider, CONFIGURED, NOT_CONFIGURED

XAI_BASE = "https://api.x.ai/v1"


class XAIProvider(AIProvider):
    name = "xai"

    def _key(self):
        return os.environ.get("XAI_API_KEY")

    def _model(self):
        return os.environ.get("XAI_MODEL", "grok-4")

    def check_provider_status(self) -> str:
        return CONFIGURED if self._key() else NOT_CONFIGURED

    async def generate_response(self, system: str, prompt: str, session_id: str | None = None) -> str:
        if not self._key():
            raise RuntimeError("XAI_API_KEY is not configured")
        payload = {"model": self._model(),
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": prompt}]}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{XAI_BASE}/chat/completions",
                                  headers={"Authorization": f"Bearer {self._key()}"}, json=payload)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]
