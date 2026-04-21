"""Valyuta kursi (USD → UZS) — CBU API dan yoki qo'lda kiritilgan kurs.

CBU API: https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/
Cache: 1 soat (har soatda yangilanadi)
"""
from __future__ import annotations
from datetime import datetime, timedelta
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Restaurant


CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/"
CACHE_TTL_HOURS = 1


async def fetch_cbu_rate() -> float | None:
    """CBU dan USD kursini olish."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(CBU_URL)
            if r.status_code != 200:
                return None
            data = r.json()
            if not data or not isinstance(data, list):
                return None
            rate_str = data[0].get("Rate")
            return float(rate_str) if rate_str else None
    except Exception:
        return None


async def get_currency_rate(restaurant_id: int, db: AsyncSession) -> float:
    """Restaurantga mos valyuta kursini qaytaradi.

    - Agar currency_auto=True va cache yangi bo'lsa — cache ishlatiladi
    - Cache eski bo'lsa — CBU dan yangilanadi
    - currency_auto=False bo'lsa — manual kurs qaytariladi
    """
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = result.scalar_one_or_none()
    if not rest:
        return 12500.0  # Default fallback

    # Qo'lda rejim
    if not rest.currency_auto:
        return rest.currency_rate_manual or 12500.0

    # Cache yangimi?
    now = datetime.utcnow()
    if rest.currency_rate_cache and rest.currency_cache_updated_at:
        age = now - rest.currency_cache_updated_at
        if age < timedelta(hours=CACHE_TTL_HOURS):
            return rest.currency_rate_cache

    # Cache eski — CBU dan yangilanadi
    cbu_rate = await fetch_cbu_rate()
    if cbu_rate:
        rest.currency_rate_cache = cbu_rate
        rest.currency_cache_updated_at = now
        await db.commit()
        return cbu_rate

    # CBU ishlamasa — mavjud cache yoki manual
    return rest.currency_rate_cache or rest.currency_rate_manual or 12500.0


def convert_usd_to_uzs(amount_usd: float, rate: float) -> float:
    return round(amount_usd * rate)


def convert_uzs_to_usd(amount_uzs: float, rate: float) -> float:
    if rate <= 0:
        return 0.0
    return round(amount_uzs / rate, 2)
