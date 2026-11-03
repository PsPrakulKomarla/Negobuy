"""Provider factory — selects the active AI provider from AI_PROVIDER (default: emergent)."""
import os
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider
from .xai_provider import XAIProvider

_REGISTRY = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "emergent": OpenAIProvider,  # universal-key path
    "xai": XAIProvider,
}
_instances: dict = {}


def active_provider_name() -> str:
    return (os.environ.get("AI_PROVIDER") or "emergent").strip().lower()


def get_provider(name: str | None = None):
    key = (name or active_provider_name())
    if key not in _REGISTRY:
        raise ValueError(f"Unknown AI provider: {key}")
    if key not in _instances:
        _instances[key] = _REGISTRY[key]()
    return _instances[key]


def provider_status() -> dict:
    out = {}
    for key in ("gemini", "openai", "xai"):
        try:
            out[key] = get_provider(key).check_provider_status()
        except Exception:
            out[key] = "NOT_CONFIGURED"
    return out
