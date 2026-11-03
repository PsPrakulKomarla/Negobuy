"""Pluggable AI provider layer for NegoBuy.
The negotiation engine and ai_service depend on this common interface, not on any
specific vendor SDK. The active provider is chosen by AI_PROVIDER (default: emergent)."""
from .provider_factory import get_provider, provider_status, active_provider_name

__all__ = ["get_provider", "provider_status", "active_provider_name"]
