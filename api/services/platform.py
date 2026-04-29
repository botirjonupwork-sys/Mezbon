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
