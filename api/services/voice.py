"""Voice pipeline — STT (Whisper) va TTS (OpenAI) integratsiyasi.

Telegram'dan kelgan voice xabar (.ogg/.opus) → Whisper STT → matn.
AI agent javobi (matn) → OpenAI TTS → audio bytes (mp3).

API kalit va modellar mezbon platforma sozlamalaridan (`platform_settings`)
o'qiladi — super-admin tomonidan boshqariladi.

Xarajatlar (taxminiy, 2026-05):
  - Whisper:  $0.006/min  (audio length bo'yicha)
  - TTS-1:    $15/1M chars  (≈ $0.015/1000 chars)
  - TTS-HD:   $30/1M chars
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from api.services import platform


OPENAI_STT_URL = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

# OpenAI TTS voice ID'lari — biz "male"/"female"'ni shu yerga moslaymiz.
# Mavjud OpenAI ovozlari: alloy, echo, fable, onyx, nova, shimmer
# nova/shimmer — ayolsifat, onyx/echo — erkak
VOICE_MAP = {
    "female": "nova",      # iliq, do'stona ayol ovozi
    "male": "onyx",        # bardam erkak ovozi
}
DEFAULT_VOICE = "nova"

# Whisper default modeli — eng arzon va ko'p tilli (uz/ru/en)
WHISPER_MODEL = "whisper-1"
TTS_MODEL = "tts-1"   # 'tts-1' (tez, arzon) yoki 'tts-1-hd' (yuqori sifat)


def _llm_api_key() -> str:
    return (platform.get("ai_llm_api_key") or os.getenv("OPENAI_API_KEY") or "").strip()


def _tts_api_key() -> str:
    """TTS uchun alohida kalit, bo'lmasa LLM kalitini ishlatamiz."""
    return (platform.get("ai_tts_api_key") or "").strip() or _llm_api_key()


def voice_for_restaurant(voice_pref: Optional[str]) -> str:
    """Restoran sozlamasi (male/female) → OpenAI TTS voice ID."""
    return VOICE_MAP.get((voice_pref or "").lower(), DEFAULT_VOICE)


def language_hint(lang_pref: Optional[str]) -> Optional[str]:
    """Restoran tilini Whisper'ga hint sifatida beramiz.

    'auto' bo'lsa — None qaytaradi (Whisper o'zi aniqlasin).
    """
    p = (lang_pref or "uz").lower()
    return None if p == "auto" else p


async def transcribe(
    audio_bytes: bytes,
    filename: str = "voice.ogg",
    language: Optional[str] = "uz",
) -> str:
    """Audio'ni Whisper API orqali matnga aylantirish.

    Telegram voice xabarlar .ogg (Opus) formatda — Whisper to'g'ridan-to'g'ri qabul qiladi.
    """
    api_key = _llm_api_key()
    if not api_key:
        raise RuntimeError("AI kalit kiritilmagan (super-admin: Sozlamalar → AI Operator)")

    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": (filename, audio_bytes, "audio/ogg")}
    data = {"model": WHISPER_MODEL, "response_format": "text"}
    if language:
        data["language"] = language

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(OPENAI_STT_URL, headers=headers, files=files, data=data)
        r.raise_for_status()
        # response_format=text bo'lsa, javob — toza matn (JSON emas)
        return r.text.strip()


async def synthesize(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """Matn → audio (mp3 bytes). Telegram .ogg voice sifatida yuborish uchun
    keyinroq konvertatsiya kerak bo'lishi mumkin, lekin Telegram .mp3'ni ham
    qabul qiladi (sendAudio yoki sendVoice OPUS bilan).
    """
    api_key = _tts_api_key()
    if not api_key:
        raise RuntimeError("AI TTS kalit kiritilmagan")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": TTS_MODEL,
        "voice": voice,
        "input": text[:4000],   # OpenAI limit
        "response_format": "opus",  # Telegram voice uchun ideal
        "speed": 1.0,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(OPENAI_TTS_URL, headers=headers, json=payload)
        r.raise_for_status()
        return r.content


def estimate_stt_cost(duration_seconds: float) -> float:
    """Whisper xarajati ($)."""
    return (duration_seconds / 60.0) * 0.006


def estimate_tts_cost(char_count: int, hd: bool = False) -> float:
    """TTS xarajati ($)."""
    rate = 30.0 if hd else 15.0   # $ per 1M chars
    return (char_count / 1_000_000.0) * rate
