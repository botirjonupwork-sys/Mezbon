"""Delivery price quote endpoint — bot uchun Yandex narxini olish.

Bu endpoint Yandex /check-price ga proxy sifatida ishlaydi:
  * Faqat NARX qaytaradi
  * Claim YARATMAYDI
  * Restoran balansidan pul KETMAYDI

Bot mijozning manzilini olgach, shu endpoint orqali real Yandex narxini olib,
mijozga ko'rsatadi va total summaga qo'shadi. Mijoz to'lasa, dispatcher
xuddi shu narxda claim yaratadi (yoki narx o'zgargan bo'lsa, qaytadan offer
oladi — bu joriy claim flow ichida hal qilinadi).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.security import is_valid_bot_secret
from database.models import Branch, Restaurant


router = APIRouter(prefix="/delivery", tags=["delivery"])


async def _require_bot_secret(
    x_bot_secret: Optional[str] = Header(None, alias="X-Bot-Secret"),
) -> bool:
    if not is_valid_bot_secret(x_bot_secret or ""):
        raise HTTPException(401, "Bot autentifikatsiyasi yaroqsiz")
    return True


@router.post("/quote")
async def delivery_quote(
    body: dict,
    _bot: bool = Depends(_require_bot_secret),
    db: AsyncSession = Depends(get_db),
):
    """Mijoz manzili uchun real Yandex narxini olish (claim emas).

    Body:
      {
        "restaurant_id": 1,         // majburiy
        "branch_id": 2,             // ixtiyoriy (pickup koordinatasi uchun)
        "dropoff_lat": 41.28,       // majburiy
        "dropoff_lon": 69.21,       // majburiy
        "weight_kg": 1.0            // ixtiyoriy (default 1.0)
      }

    Qaytaradi:
      success: {"ok": True, "price": 18200.0, "currency": "UZS", "eta_minutes": 25}
      no coverage: {"ok": False, "code": "no_coverage", "message": "..."}
      provider != yandex: {"ok": False, "code": "provider_not_yandex"}
      network/server xato: {"ok": False, "code": "error", "message": "..."}
    """
    from api.services.yandex_delivery import YandexDeliveryClient

    restaurant_id = body.get("restaurant_id")
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id majburiy")

    dropoff_lat = body.get("dropoff_lat")
    dropoff_lon = body.get("dropoff_lon")
    if dropoff_lat is None or dropoff_lon is None:
        raise HTTPException(400, "dropoff_lat va dropoff_lon majburiy")

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == int(restaurant_id))
    )).scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    if (rest.delivery_provider or "own") != "yandex":
        return {
            "ok": False,
            "code": "provider_not_yandex",
            "message": "Bu restoran Yandex dastavkasini ishlatmaydi",
        }

    pickup_lat = rest.restaurant_lat
    pickup_lon = rest.restaurant_lon
    branch_id = body.get("branch_id")
    if branch_id:
        br = (await db.execute(
            select(Branch).where(
                Branch.id == int(branch_id),
                Branch.restaurant_id == rest.id,
            )
        )).scalar_one_or_none()
        if br and br.latitude and br.longitude:
            pickup_lat = br.latitude
            pickup_lon = br.longitude

    if pickup_lat is None or pickup_lon is None:
        raise HTTPException(400, "Pickup koordinatalari sozlanmagan")

    client = YandexDeliveryClient(
        api_token=rest.yandex_api_token or "",
        test_mode=bool(rest.yandex_test_mode),
    )
    return await client.quote_price(
        pickup_lat=float(pickup_lat),
        pickup_lon=float(pickup_lon),
        dropoff_lat=float(dropoff_lat),
        dropoff_lon=float(dropoff_lon),
        weight_kg=float(body.get("weight_kg") or 1.0),
    )
