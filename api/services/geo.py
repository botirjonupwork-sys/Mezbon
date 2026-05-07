"""Geografik yordamchi funksiyalar.

- `haversine_km()` — ikki koordinata orasidagi masofa (kilometrda)
- `find_nearest_branch()` — mijoz koordinatalari bo'yicha eng yaqin faol filial

Telegram bot mijoz koordinatasini yuborganda yoki webapp lat/lon bersa,
order yaratish vaqtida shu funksiya filialni avtomatik tanlaydi.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Branch


EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Yer sirti bo'yicha ikki nuqta orasidagi masofa (km).

    Haversine formulasi — pivotsiz, juda aniq (10–100m xato 1000km gacha).
    """
    if None in (lat1, lon1, lat2, lon2):
        return float("inf")

    p1 = radians(float(lat1))
    p2 = radians(float(lat2))
    dphi = p2 - p1
    dlmb = radians(float(lon2) - float(lon1))

    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    c = 2 * asin(sqrt(a))
    return EARTH_RADIUS_KM * c


async def find_nearest_branch(
    db: AsyncSession,
    *,
    restaurant_id: int,
    lat: float,
    lon: float,
    only_active: bool = True,
) -> Optional[Branch]:
    """Restorannning eng yaqin filialini topadi (Haversine bo'yicha).

    Args:
        restaurant_id: filial qaysi restoranga tegishli
        lat, lon: mijoz koordinatasi
        only_active: faqat is_active filiallar (default True)

    Qaytaradi: `Branch` obyekti yoki None (filial yo'q yoki koordinata noto'g'ri).

    Eslatma: bu funksiya O(N) — kichik restoranlar uchun yetarli.
    Yuqori scale uchun: PostGIS yoki spatial index kerak bo'ladi.
    """
    if lat is None or lon is None:
        return None

    q = select(Branch).where(Branch.restaurant_id == restaurant_id)
    if only_active:
        q = q.where(Branch.is_active == True)
    branches = (await db.execute(q)).scalars().all()
    if not branches:
        return None

    nearest: Optional[Branch] = None
    nearest_dist = float("inf")
    for b in branches:
        if b.latitude is None or b.longitude is None:
            continue
        d = haversine_km(lat, lon, b.latitude, b.longitude)
        if d < nearest_dist:
            nearest_dist = d
            nearest = b

    # Hech qaysi filialda lat/lon bo'lmasa, fallback — birinchi faol filial
    if nearest is None and branches:
        return branches[0]
    return nearest


async def list_branches_with_distance(
    db: AsyncSession,
    *,
    restaurant_id: int,
    lat: float,
    lon: float,
    only_active: bool = True,
) -> list[dict]:
    """Barcha filiallarni masofa bo'yicha tartiblangan ro'yxat.

    Frontend uchun (mijoz "yana yaqinroq filial bormi?" ko'rmoqchi bo'lsa).
    """
    q = select(Branch).where(Branch.restaurant_id == restaurant_id)
    if only_active:
        q = q.where(Branch.is_active == True)
    rows = (await db.execute(q)).scalars().all()

    out = []
    for b in rows:
        d = (haversine_km(lat, lon, b.latitude, b.longitude)
             if b.latitude is not None and b.longitude is not None else None)
        out.append({
            "id": b.id, "name": b.name, "address": b.address,
            "latitude": b.latitude, "longitude": b.longitude,
            "distance_km": round(d, 2) if d is not None else None,
        })
    out.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0))
    return out
