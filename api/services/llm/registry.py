"""Provayder ro'yxati va platform_settings'dan o'qish."""
from __future__ import annotations

from typing import Optional

from .base import LLMProvider
from .openai_provider import OpenAIProvider
from .groq_provider import GroqProvider
from .anthropic_provider import AnthropicProvider
from .gemini_provider import GeminiProvider


PROVIDERS: dict[str, LLMProvider] = {
    "openai": OpenAIProvider(),
    "groq": GroqProvider(),
    "anthropic": AnthropicProvider(),
    "gemini": GeminiProvider(),
}


def get_provider_by_name(name: str) -> Optional[LLMProvider]:
    return PROVIDERS.get((name or "").lower())


def get_provider() -> LLMProvider:
    """Platform sozlamasidan joriy provayderni qaytaradi.

    Default: OpenAI (eski deployment'lar uchun backward compat).
    """
    from api.services import platform
    name = (platform.get("ai_llm_provider") or "openai").lower()
    return PROVIDERS.get(name, PROVIDERS["openai"])


def get_provider_api_key(provider_name: Optional[str] = None) -> str:
    """Tanlangan provayder uchun API kalitni platform_settings'dan o'qish.

    Yangi format: ai_llm_api_keys = {"openai": "...", "groq": "...", ...}
    Eski format (backward compat): ai_llm_api_key (faqat openai uchun)
    """
    from api.services import platform
    import os

    name = (provider_name or platform.get("ai_llm_provider") or "openai").lower()
    keys = platform.get("ai_llm_api_keys") or {}
    if isinstance(keys, dict) and keys.get(name):
        return str(keys[name]).strip()
    # Eski format — faqat OpenAI uchun
    if name == "openai":
        legacy = platform.get("ai_llm_api_key")
        if legacy:
            return str(legacy).strip()
        return (os.getenv("OPENAI_API_KEY") or "").strip()
    return ""


def list_providers() -> list[dict]:
    """UI uchun barcha provayderlar metama'lumotlari."""
    return [p.info() for p in PROVIDERS.values()]
