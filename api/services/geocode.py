"""Manzil matni → koordinata (forward geocoding, Nominatim/OSM).

AI telefon operatori manzilni MATN sifatida oladi (ovozda xarita pin yo'q).
Yetkazib berish/koordinata uchun matnni geokodlash kerak. Nominatim bepul.

Eslatma: Nominatim 1 so'rov/sekund cheklovi va User-Agent talab qiladi.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_UA = "MuhsinaDollar/1.0 (restaurant ordering)"


async def geocode_address(text: str, city_hint: str = "Toshkent") -> Optional[tuple[float, float]]:
    """Manzil matnidan (lat, lon) qaytaradi yoki topilmasa None.

    O'zbekistonga cheklaymiz (countrycodes=uz) va shahar maslahatini qo'shamiz —
    aniqlikni oshiradi.
    """
    text = (text or "").strip()
    if len(text) < 3:
        return None
    q = text if city_hint.lower() in text.lower() else f"{text}, {city_hint}"
    params = {"q": f"{q}, Uzbekistan", "format": "json", "limit": 1, "countrycodes": "uz"}
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": _UA}) as client:
            r = await client.get(_NOMINATIM, params=params)
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, list) and data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        log.warning("geocode_address xato: %s", e)
    return None
