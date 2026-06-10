"""Groq adapter — OpenAI-mos API. Asosan OpenAIProvider'ni qayta ishlatamiz."""
from __future__ import annotations

from typing import ClassVar

from .base import ModelInfo
from .openai_provider import OpenAIProvider


class GroqProvider(OpenAIProvider):
    name = "groq"
    display_name = "Groq (Llama, Mixtral — BEPUL)"
    requires_billing = False
    api_key_prefix = "gsk_"
    api_key_help_url = "https://console.groq.com/keys"

    BASE_URL: ClassVar[str] = "https://api.groq.com/openai/v1"

    @property
    def models(self):
        # 2026-05 holatiga ko'ra Groq'da faol modellar.
        # Eskirganlari (gemma2-9b-it, mixtral-8x7b, llama-3.1-70b) olib tashlangan.
        return [
            ModelInfo(
                "meta-llama/llama-4-scout-17b-16e-instruct",
                "Llama 4 Scout 17B (yangi, balansli) ⭐",
                free=True, context=128_000,
                notes="500k TPD, 30k TPM — restoran uchun eng yaxshi tanlov",
            ),
            ModelInfo(
                "llama-3.3-70b-versatile", "Llama 3.3 70B (eng aqlli)",
                free=True, context=128_000,
                notes="100k TPD (kam) — ko'p buyurtmaga yetmaydi",
            ),
            ModelInfo(
                "llama-3.1-8b-instant", "Llama 3.1 8B Instant (eng tez)",
                free=True, context=128_000,
                notes="500k TPD, 6k TPM — sodda vazifalarga",
            ),
            ModelInfo(
                "openai/gpt-oss-120b", "GPT-OSS 120B (OpenAI open-source)",
                free=True, context=128_000, notes="Kuchli, lekin sekinroq",
            ),
            ModelInfo(
                "openai/gpt-oss-20b", "GPT-OSS 20B",
                free=True, context=128_000, notes="Tez, o'rta kuchli",
            ),
            ModelInfo(
                "qwen/qwen3-32b", "Qwen 3 32B (multilingual)",
                free=True, context=128_000, notes="Ko'p tilli qo'llab-quvvatlash",
            ),
        ]
