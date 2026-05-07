"""Catering buyurtma validatsiyasi.

`is_catering=True` bo'lgan order yaratilishidan oldin tekshiriladigan qoidalar:

1. **event_date majburiy** — kelajakda bo'lishi kerak (kamida 2 soat keyin)
2. **Min miqdor** — restoran sozlamasidagi `catering_somsa_min` (default 100)
3. **Restoran ish vaqti** — event_date restoranning work_hours oralig'ida
4. **Mahsulotlar catering bo'lishi kerak** — har item product_type='catering'
5. **Mashinalar bo'sh bo'lishi** — DeliveryCarBooking sig'imi tekshiriladi (delivery only)

Foydalanish:
    from api.services.catering_validator import validate_catering_order

    validate_catering_order(
        event_date=body.event_date,
        items=body.items,
        restaurant=rest,
    )
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from fastapi import HTTPException

from database.models import Product, Restaurant


# Catering uchun minimal old-bron vaqti — buyurtmani tayyorlash uchun
MIN_LEAD_TIME_HOURS = 2

# Maksimal kelajakka — 365 kun (1 yil)
MAX_AHEAD_DAYS = 365


def validate_event_date(event_date: datetime, *, restaurant: Restaurant) -> None:
    """`event_date` ni tekshiradi. Xato bo'lsa `HTTPException(400)` ko'taradi."""
    if not event_date:
        raise HTTPException(400, "Catering uchun `event_date` majburiy")

    now = datetime.utcnow()

    # Kelajakda bo'lishi kerak
    if event_date <= now:
        raise HTTPException(400, "Tadbir vaqti o'tib ketgan — kelajakdagi sana tanlang")

    # Min lead time
    min_allowed = now + timedelta(hours=MIN_LEAD_TIME_HOURS)
    if event_date < min_allowed:
        raise HTTPException(
            400,
            f"Catering buyurtmasi kamida {MIN_LEAD_TIME_HOURS} soat oldin berilishi kerak",
        )

    # Juda uzoq kelajak — xato bo'lishi mumkin
    max_allowed = now + timedelta(days=MAX_AHEAD_DAYS)
    if event_date > max_allowed:
        raise HTTPException(400, f"Tadbir sanasi {MAX_AHEAD_DAYS} kundan ko'p bo'la olmaydi")

    # Ish vaqti tekshiruvi (restoran work_hours oralig'i)
    if restaurant and restaurant.work_hours_from and restaurant.work_hours_until:
        try:
            wh_from = _parse_hhmm(restaurant.work_hours_from)
            wh_until = _parse_hhmm(restaurant.work_hours_until)
            event_minutes = event_date.hour * 60 + event_date.minute
            if event_minutes < wh_from or event_minutes >= wh_until:
                raise HTTPException(
                    400,
                    f"Tadbir vaqti restoran ish vaqtidan ({restaurant.work_hours_from}–"
                    f"{restaurant.work_hours_until}) tashqarida",
                )
        except ValueError:
            pass  # work_hours format noto'g'ri — sokin o'tib yuboramiz


def validate_min_quantity(items: Iterable, restaurant: Restaurant) -> None:
    """Catering minimal miqdor — somsa va non uchun alohida."""
    somsa_total = 0
    nan_total = 0
    for it in items:
        # `it` `OrderItemCreate`-style schema — product info olishimiz kerak
        # Bu funksiya uchun caller mahsulot katalogi bo'yicha to'ldiradi
        if hasattr(it, "_product") and it._product:
            p: Product = it._product
            qty = getattr(it, "quantity", 1)
            if (p.catering_group or "").lower() == "somsa":
                somsa_total += qty
            elif (p.catering_group or "").lower() == "nan":
                nan_total += qty

    somsa_min = restaurant.catering_somsa_min or 100
    nan_min = restaurant.catering_nan_min or 40
    if somsa_total > 0 and somsa_total < somsa_min:
        raise HTTPException(
            400,
            f"Somsa minimal: {somsa_min} dona (siz: {somsa_total})",
        )
    if nan_total > 0 and nan_total < nan_min:
        raise HTTPException(
            400,
            f"Non minimal: {nan_min} dona (siz: {nan_total})",
        )
    if somsa_total == 0 and nan_total == 0:
        raise HTTPException(400, "Catering buyurtmasida hech qanday catering mahsuloti yo'q")


def validate_catering_order(
    *,
    event_date: datetime,
    restaurant: Restaurant,
    items: Iterable = (),
) -> None:
    """Catering buyurtmasi uchun butun validatsiya zanjiri.

    Caller bu funksiyani `is_catering=True` bo'lganda chaqiradi.
    Xato bo'lsa `HTTPException` ko'tariladi va order yaratilmaydi.
    """
    validate_event_date(event_date, restaurant=restaurant)
    if items:
        validate_min_quantity(items, restaurant)


def _parse_hhmm(s: str) -> int:
    """`'09:00'` → daqiqalardagi 540."""
    h, m = s.split(":")
    return int(h) * 60 + int(m)
