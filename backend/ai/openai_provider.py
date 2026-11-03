"""OpenAI / Emergent provider — emergentintegrations universal key (existing NegoBuy path)."""
import os
from .base_provider import AIProvider, CONFIGURED, NOT_CONFIGURED


class OpenAIProvider(AIProvider):
    name = "openai"

    def _key(self):
        return os.environ.get("EMERGENT_LLM_KEY")

    def _model(self):
        return os.environ.get("LLM_MODEL", "gpt-5.6-terra")

    def check_provider_status(self) -> str:
        return CONFIGURED if self._key() else NOT_CONFIGURED

    async def generate_response(self, system: str, prompt: str, session_id: str | None = None) -> str:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        if not self._key():
            raise RuntimeError("EMERGENT_LLM_KEY is not configured")
        chat = LlmChat(api_key=self._key(), session_id=session_id or "default",
                       system_message=system).with_model("openai", self._model())
        resp = await chat.send_message(UserMessage(text=prompt))
        return resp if isinstance(resp, str) else str(resp)
