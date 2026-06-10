"""Global platforma sozlamalari (super-admin tomonidan boshqariladi).

`platform_settings.json` faylga saqlanadi (single-source-of-truth, oddiy),
tezkor o'qish uchun in-memory cache bilan. Maintenance mode bayrog'i shu
yerda yashaydi — middleware har so'rovda shu funksiyaga murojaat qiladi.
"""
from __future__ import annotations

import json
import os
from threading import RLock
from typing import Any

_FILE = os.path.abspath(os.path.join(os.getcwd(), "platform_settings.json"))
_DEFAULT = {
    "maintenance_mode": False,
    "maintenance_message": "Texnik tanaffus. Tez orada qaytamiz.",
    # AI Call Operator — mezbon platforma boshqaradi (barcha restoranlar uchun yagona)
    "ai_llm_provider": "openai",          # 'openai' | 'groq' | 'anthropic' | 'gemini'
    "ai_llm_model": "gpt-4o-mini",        # provayder model ID
    "ai_llm_api_keys": {},                # {"openai": "sk-...", "groq": "gsk_...", "anthropic": "sk-ant-...", "gemini": "AIza..."}
    "ai_llm_api_key": "",                 # DEPRECATED — backward compat (faqat openai); endi ai_llm_api_keys ishlatiladi
    "ai_stt_provider": "openai",          # 'openai' (Whisper) | 'groq' (Groq Whisper — bepul)
    "ai_tts_provider": "openai",          # 'openai' | 'none' (matn-only rejim)
    "ai_voice_gateway": "telegram",       # 'telegram' | 'vapi' | 'twilio'
    # Payme Subscribe — restoran obunalarini avtomatik undirish (PLATFORMA kassasi).
    # Bu credential'lar platforma yuridik shaxsi (Mezbon) kassasiga tegishli — restoranniki emas.
    "payme_subscribe_merchant_id": "",    # Subscribe kassa ID (X-Auth)
    "payme_subscribe_key": "",            # Subscribe kassa kaliti (receipts uchun X-Auth: id:key)
    "payme_subscribe_test_mode": True,    # True → checkout.test.paycom.uz/api (sandbox)
}

_cache: dict[str, Any] | None = None
_lock = RLock()


def _load() -> dict[str, Any]:
    if not os.path.exists(_FILE):
        return dict(_DEFAULT)
    try:
        with open(_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # Defaultlar bilan to'ldiramiz (yangi keylar qo'shilganda backward compat)
        merged = dict(_DEFAULT)
        merged.update(data or {})
        return merged
    except Exception:
        return dict(_DEFAULT)


def get_all() -> dict[str, Any]:
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load()
        return dict(_cache)


def get(key: str, default: Any = None) -> Any:
    return get_all().get(key, default)


def set_many(updates: dict[str, Any]) -> dict[str, Any]:
    """Bir nechta kalitni atomar yangilaydi va diskka yozadi."""
    global _cache
    with _lock:
        current = get_all()
        current.update(updates)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        _cache = current
        return dict(_cache)


def is_maintenance() -> bool:
    return bool(get("maintenance_mode", False))
