"""LLM provider abstraktsiyasi.

4 ta provayder qo'llab-quvvatlanadi: OpenAI, Groq, Anthropic (Claude), Google Gemini.

Foydalanish:
    from api.services.llm import get_provider, list_providers

    provider = get_provider()              # platform_settings'dan tanlanadi
    result = await provider.chat(api_key, model, messages, tools)
    # result: {"content": str, "tool_calls": [...], "usage": {...}}

Har bir provayder OpenAI-shaklidagi `messages` va `tools` formatini qabul qiladi va
bir xil shaklda javob qaytaradi — `ai_agent.py` ichida farq bilinmaydi.
"""
from __future__ import annotations

from .base import LLMProvider, ChatResult
from .openai_provider import OpenAIProvider
from .groq_provider import GroqProvider
from .anthropic_provider import AnthropicProvider
from .gemini_provider import GeminiProvider
from .registry import PROVIDERS, get_provider, list_providers, get_provider_by_name

__all__ = [
    "LLMProvider", "ChatResult",
    "OpenAIProvider", "GroqProvider", "AnthropicProvider", "GeminiProvider",
    "PROVIDERS", "get_provider", "list_providers", "get_provider_by_name",
]
