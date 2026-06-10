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
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
AISHA_STT_URL = "https://back.aisha.group/api/v1/stt/post/"

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

# O'zbekcha STT uchun statik prompt — restoran domeniga oid lug'at.
# Whisper bu matnni kontekst sifatida ishlatadi va undagi so'zlarni yaxshiroq tanidi.
# MUHIM: 224 token limiti bor — qisqa va mavzuga aniq.
_UZ_RESTAURANT_PROMPT = (
    "Restoran buyurtmasi. "
    "Mahsulotlar: somsa, manti, palov, lavash, sho'rva, lag'mon, mastava, "
    "kabob, shashlik, non, choy, qaymoq, qatiq. "
    "Raqamlar: bir, ikki, uch, to'rt, besh, olti, yetti, sakkiz, to'qqiz, o'n, "
    "yigirma, o'ttiz, qirq, ellik, yuz. "
    "Manzil: ko'cha, mavze, uy, kvartira, podyezd, qavat. "
    "Tumanlar: Chilonzor, Yunusobod, Yashnobod, Olmazor, Sergeli, Bektemir, "
    "Mirzo Ulug'bek, Yakkasaroy, Mirobod, Shayxontohur, Uchtepa. "
    "Iboralar: yetkazib berish, olib ketish, tasdiqlayman, bekor qilaman."
)


def build_whisper_prompt(menu_items: Optional[list[str]] = None) -> str:
    """Whisper'ga yuboriladigan kontekst prompt'ni quradi.

    Statik o'zbek restoran lug'ati + (agar berilgan bo'lsa) shu restoranning
    o'ziga xos menyu nomlari. Whisper shu so'zlarni yaxshiroq tanish uchun
    ishlatadi.

    Args:
        menu_items: Restoran menyusidagi mahsulot nomlari (max 30 ta).

    Returns:
        Prompt matni (max ~200 token).
    """
    parts = [_UZ_RESTAURANT_PROMPT]
    if menu_items:
        # Faqat unique va qisqa nomlarni olamiz, 30 tagacha
        seen = set()
        items = []
        for name in menu_items:
            if not name:
                continue
            n = name.strip()
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(n)
            if len(items) >= 30:
                break
        if items:
            parts.append(f"Shu restoran menyusi: {', '.join(items)}.")
    return " ".join(parts)


def _stt_provider_name() -> str:
    """STT provayder nomi: 'openai' yoki 'groq'."""
    return (platform.get("ai_stt_provider") or "openai").lower()


def _stt_api_key() -> str:
    """STT uchun kalit — tanlangan STT provayder bo'yicha."""
    from api.services.llm.registry import get_provider_api_key
    return get_provider_api_key(_stt_provider_name())


def _tts_api_key() -> str:
    """OpenAI TTS uchun kalit (faqat OpenAI)."""
    from api.services.llm.registry import get_provider_api_key
    return get_provider_api_key("openai")


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
    prompt: Optional[str] = None,
    menu_items: Optional[list[str]] = None,
) -> str:
    """Audio'ni Whisper API orqali matnga aylantirish.

    STT provayder platform sozlamasiga qarab tanlanadi:
    - 'openai': OpenAI Whisper (whisper-1, ~$0.006/daq)
    - 'groq':   Groq Whisper (whisper-large-v3, BEPUL)

    Args:
        audio_bytes: Audio fayl bytes (ogg/mp3/wav).
        filename: Fayl nomi (MIME type aniqlash uchun).
        language: ISO til kodi ("uz", "ru", ...) yoki None.
        prompt: Whisper kontekst prompt'i (224 token limiti). Bo'sh bo'lsa
                avtomatik o'zbek restoran lug'ati ishlatiladi.
        menu_items: Restoran menyusi nomlari — prompt'ga qo'shiladi.
    """
    provider = _stt_provider_name()
    api_key = _stt_api_key()
    if not api_key:
        raise RuntimeError(
            f"STT kalit yo'q (provayder: {provider}). "
            "Super-admin: Sozlamalar → AI Operator'da kalitni kiriting."
        )

    # Aisha — O'zbek tili uchun maxsus o'rgatilgan (yangi mahalliy provayder)
    if provider == "aisha":
        return await _transcribe_aisha(audio_bytes, filename, api_key, language)

    if provider == "groq":
        url = GROQ_STT_URL
        model = "whisper-large-v3"   # Groq Whisper modeli
    else:
        url = OPENAI_STT_URL
        model = WHISPER_MODEL

    # Prompt — agar berilmagan bo'lsa, avtomatik o'zbek restoran lug'atini quramiz.
    # Faqat uz/ru tillarida prompt foydali (en/auto'da Whisper o'zi yaxshi).
    if prompt is None and (language or "").lower() in ("uz", "ru"):
        prompt = build_whisper_prompt(menu_items)

    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": (filename, audio_bytes, "audio/ogg")}
    data = {"model": model, "response_format": "text"}
    if language:
        data["language"] = language
    if prompt:
        # Whisper prompt limiti: Groq → 896 chars, OpenAI → ~224 token (~1200 chars).
        # Eng past chegarani olamiz — 880 (xavfsizlik marjin'i bilan).
        data["prompt"] = prompt[:880]

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, files=files, data=data)
        if r.status_code >= 400:
            # Batafsil xato — Groq/OpenAI javobini saqlab xato qaytaramiz
            try:
                body = r.json()
                detail = body.get("error", {})
                if isinstance(detail, dict):
                    msg = detail.get("message") or str(detail)
                else:
                    msg = str(detail)
            except Exception:
                msg = r.text[:400]
            raise RuntimeError(f"STT API xatosi ({r.status_code}): {msg}")
        return r.text.strip()


# ── Aisha STT (O'zbek mahalliy provayder) ────────────────────────────────

async def _transcribe_aisha(
    audio_bytes: bytes,
    filename: str,
    api_key: str,
    language: Optional[str] = None,
) -> str:
    """Aisha STT API — O'zbek tili uchun ~90% aniqlik (Whisper'dan 2x yaxshi).

    Endpoint: POST https://back.aisha.group/api/v1/stt/post/
    Auth:     X-Api-Key header
    Body:     multipart/form-data (audio file)
    Pricing:  425 so'm / daqiqa
    """
    headers = {"X-Api-Key": api_key}
    # MIME type'ni fayl kengaytmasiga qarab tanlaymiz
    fn = (filename or "").lower()
    if fn.endswith(".mp3"):
        mime = "audio/mpeg"
    elif fn.endswith(".wav"):
        mime = "audio/wav"
    else:
        mime = "audio/ogg"
    files = {"audio": (filename or "voice.ogg", audio_bytes, mime)}
    data: dict = {}
    if language:
        # Aisha "uz" va "ru" tillarini qo'llab-quvvatlaydi
        data["language"] = language

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(AISHA_STT_URL, headers=headers, files=files, data=data)
        if r.status_code >= 400:
            try:
                body = r.json()
                msg = body.get("detail") or body.get("error") or body.get("message") or str(body)
            except Exception:
                msg = r.text[:400]
            raise RuntimeError(f"Aisha STT xatosi ({r.status_code}): {msg}")
        try:
            body = r.json()
        except Exception:
            return r.text.strip()
        # Aisha javob formati: turli versiyalarda farq qilishi mumkin —
        # 'text' / 'transcript' / 'result' kalitlarini sinab ko'ramiz
        if isinstance(body, dict):
            for k in ("text", "transcript", "result", "data"):
                v = body.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
                if isinstance(v, dict):
                    for kk in ("text", "transcript", "result"):
                        vv = v.get(kk)
                        if isinstance(vv, str) and vv.strip():
                            return vv.strip()
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
