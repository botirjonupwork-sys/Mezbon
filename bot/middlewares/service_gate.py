"""Xizmat darvozasi — restoran bloklangan/suspended bo'lsa botni to'xtatadi.

Restoran:
  * super-admin tomonidan bloklansa (status='blocked'), yoki
  * tarif + 10 kun grace tugab suspended bo'lsa
bot mijozlarga xizmat ko'rsatmaydi — block xabarini ko'rsatib, handler chaqirilmaydi.

Holat API'dan olinadi va ~30s keshlanadi (har xabarda API'ni urmaslik uchun).
API'ga ulanib bo'lmasa — FAIL-OPEN: bloklanmaydi (vaqtinchalik API uzilishi
to'lovini to'lagan restoranni bloklab qo'ymasin).
"""
from __future__ import annotations

import time
from typing import Any, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import api_client

_CACHE_TTL = 30.0
_cache: dict[int, tuple[float, dict]] = {}   # rid -> (expires_monotonic, state)


async def _get_state(rid: int) -> dict | None:
    now = time.monotonic()
    cached = _cache.get(rid)
    if cached and cached[0] > now:
        return cached[1]
    try:
        state = await api_client.get_service_state()
    except Exception:
        # Fail-open: API muammosida oxirgi ma'lum holatni qaytaramiz (bo'lmasa bloklamaymiz)
        return cached[1] if cached else None
    _cache[rid] = (now + _CACHE_TTL, state)
    return state


class ServiceGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)):
            state = await _get_state(api_client.get_restaurant_id())
            if state and state.get("blocked"):
                text = state.get("message") or "🔴 Restoran hozircha xizmat ko'rsatmayapti."
                try:
                    if isinstance(event, Message):
                        await event.answer(text)
                    else:  # CallbackQuery
                        await event.answer(text, show_alert=True)
                except Exception:
                    pass
                return  # handler chaqirilmaydi — xizmat to'xtatildi
        return await handler(event, data)
