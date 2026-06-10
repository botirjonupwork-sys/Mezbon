"""Kuryer bot uchun xizmat darvozasi — restoran bloklangan/suspended bo'lsa
kuryer ham buyurtmalarni qabul qila olmasligi kerak.

Customer botdagi ServiceGate'ga mos, lekin courier_bot mustaqil ishlaydi:
holatni `/restaurants/{rid}/info` ochiq endpoint'idan oladi (BOT_RESTAURANT_ID),
~30s keshlaydi va API uzilishida FAIL-OPEN qiladi.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable

import httpx
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

API_URL = os.getenv("API_URL", "http://localhost:8000")
RESTAURANT_ID = int(os.getenv("BOT_RESTAURANT_ID") or "1")

_CACHE_TTL = 30.0
_cache: tuple[float, dict] | None = None


async def _get_state() -> dict | None:
    global _cache
    now = time.monotonic()
    if _cache and _cache[0] > now:
        return _cache[1]
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(f"{API_URL}/restaurants/{RESTAURANT_ID}/info")
            r.raise_for_status()
            d = r.json()
        state = {
            "blocked": bool(d.get("service_blocked")),
            "message": d.get("service_message") or "",
        }
    except Exception:
        # Fail-open: API muammosida oxirgi ma'lum holat (bo'lmasa bloklamaymiz)
        return _cache[1] if _cache else None
    _cache = (now + _CACHE_TTL, state)
    return state


class ServiceGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)):
            state = await _get_state()
            if state and state.get("blocked"):
                text = state.get("message") or "🔴 Restoran hozircha xizmat ko'rsatmayapti."
                try:
                    if isinstance(event, Message):
                        await event.answer(text)
                    else:
                        await event.answer(text, show_alert=True)
                except Exception:
                    pass
                return  # handler chaqirilmaydi
        return await handler(event, data)
