"""Resource Management — filial darajasidagi mashinalar boshqaruvi.

**Faza 3**: car_count va order_cycle endi `Branch` modelida (har filial alohida).
`DeliveryCarBooking.branch_id` MAJBURIY — booking har doim aniq filialga yoziladi.

Algoritm:
1. Order yaratilayotgan paytda `find_nearest_branch()` mijoz lat/lon orqali
   filialni aniqlaydi va `order.branch_id` o'rnatadi.
2. `book_car_for_order(order)` shu filialdagi N ta mashinadan bittasini band qiladi.
3. `find_available_car(restaurant_id, branch_id, ...)` faqat shu filial mashinalarini
   tekshiradi — bir filial to'liq bandi paytida boshqa filial mashinalari hisobga
   olinmaydi.

Backward compat:
- `Restaurant.delivery_car_count` va `order_cycle_minutes` mavjud, lekin
  yangi kod faqat Branch'dan o'qiydi.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.logging_config import log_critical
from database.models import Branch, DeliveryCarBooking, Order, Restaurant


CATERING_DURATION_MINUTES = 240


class CarCapacityExceeded(Exception):
    """Filial mashinalari to'liq band — yangi buyurtma rad qilinishi kerak."""
    def __init__(self, restaurant_id: int, branch_id: int, window: tuple[datetime, datetime]):
        self.restaurant_id = restaurant_id
        self.branch_id = branch_id
        self.window = window
        super().__init__(
            f"Branch #{branch_id} (restaurant #{restaurant_id}) mashinalari to'liq band "
            f"({window[0]} → {window[1]})"
        )


async def _get_branch_capacity(
    db: AsyncSession, *, restaurant_id: int, branch_id: int,
) -> tuple[int, int]:
    """Filialning (car_count, cycle_minutes) qaytaradi. Default'ga fallback bilan."""
    branch = (await db.execute(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.restaurant_id == restaurant_id,
        )
    )).scalar_one_or_none()
    if branch:
        return (
            max(1, int(branch.delivery_car_count or 5)),
            max(15, int(branch.order_cycle_minutes or 120)),
        )
    # Filial yo'q yoki boshqa restoranga tegishli — restaurant defaultiga fallback
    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        return (5, 120)
    return (
        max(1, int(rest.delivery_car_count or 5)),
        max(15, int(rest.order_cycle_minutes or 120)),
    )


async def find_available_car(
    db: AsyncSession,
    *,
    restaurant_id: int,
    branch_id: int,
    reserved_from: datetime,
    reserved_until: datetime,
) -> Optional[int]:
    """Filial mashinalari ichida bo'sh `car_index`ni qaytaradi (0..N-1).

    Booking faqat shu filialga tegishli'larini hisobga oladi.
    """
    car_count, _ = await _get_branch_capacity(
        db, restaurant_id=restaurant_id, branch_id=branch_id,
    )

    overlapping = (await db.execute(
        select(DeliveryCarBooking.car_index).where(
            DeliveryCarBooking.restaurant_id == restaurant_id,
            DeliveryCarBooking.branch_id == branch_id,
            DeliveryCarBooking.status == "active",
            and_(
                DeliveryCarBooking.reserved_from < reserved_until,
                DeliveryCarBooking.reserved_until > reserved_from,
            ),
        )
    )).scalars().all()

    busy = set(overlapping)
    for idx in range(car_count):
        if idx not in busy:
            return idx
    return None


async def book_car_for_order(
    db: AsyncSession,
    *,
    order: Order,
    is_catering: bool = False,
    event_date: Optional[datetime] = None,
) -> Optional[DeliveryCarBooking]:
    """Buyurtma uchun filial mashinasini band qiladi.

    `order.branch_id` MAJBURIY — yo'q bo'lsa `ValueError` ko'tariladi.
    """
    if order.delivery_type and order.delivery_type.value != "delivery":
        return None  # Pickup/onsite uchun mashina kerak emas

    if not order.branch_id:
        raise ValueError("Order.branch_id majburiy — book_car_for_order chaqirilishidan oldin tanlang")

    _, cycle = await _get_branch_capacity(
        db, restaurant_id=order.restaurant_id, branch_id=order.branch_id,
    )

    if is_catering and event_date:
        reserved_from = event_date
        reserved_until = event_date + timedelta(minutes=CATERING_DURATION_MINUTES)
    else:
        reserved_from = datetime.utcnow()
        reserved_until = reserved_from + timedelta(minutes=cycle)

    car_index = await find_available_car(
        db,
        restaurant_id=order.restaurant_id,
        branch_id=order.branch_id,
        reserved_from=reserved_from,
        reserved_until=reserved_until,
    )
    if car_index is None:
        log_critical(
            "resources", "Filial mashinalari to'liq band",
            restaurant_id=order.restaurant_id, branch_id=order.branch_id,
            order_id=order.id,
            window_from=reserved_from.isoformat(),
            window_until=reserved_until.isoformat(),
        )
        raise CarCapacityExceeded(
            order.restaurant_id, order.branch_id, (reserved_from, reserved_until),
        )

    booking = DeliveryCarBooking(
        restaurant_id=order.restaurant_id,
        branch_id=order.branch_id,
        order_id=order.id,
        car_index=car_index,
        reserved_from=reserved_from,
        reserved_until=reserved_until,
        status="active",
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


async def release_car(db: AsyncSession, *, order_id: int) -> int:
    """Buyurtma yakunlangach booking'ni 'completed' qiladi."""
    bookings = (await db.execute(
        select(DeliveryCarBooking).where(
            DeliveryCarBooking.order_id == order_id,
            DeliveryCarBooking.status == "active",
        )
    )).scalars().all()
    for b in bookings:
        b.status = "completed"
    if bookings:
        await db.commit()
    return len(bookings)


async def get_capacity_snapshot(
    db: AsyncSession,
    *,
    restaurant_id: int,
    branch_id: int,
    at: Optional[datetime] = None,
) -> dict:
    """Filial mashinalari real-time holati. Frontend widget va available-slots uchun."""
    car_count, _ = await _get_branch_capacity(
        db, restaurant_id=restaurant_id, branch_id=branch_id,
    )
    moment = at or datetime.utcnow()

    active = (await db.execute(
        select(DeliveryCarBooking).where(
            DeliveryCarBooking.restaurant_id == restaurant_id,
            DeliveryCarBooking.branch_id == branch_id,
            DeliveryCarBooking.status == "active",
            DeliveryCarBooking.reserved_from <= moment,
            DeliveryCarBooking.reserved_until > moment,
        ).order_by(DeliveryCarBooking.reserved_until)
    )).scalars().all()

    by_idx: dict[int, DeliveryCarBooking] = {}
    for b in active:
        if b.car_index < car_count and b.car_index not in by_idx:
            by_idx[b.car_index] = b

    cars = []
    for idx in range(car_count):
        b = by_idx.get(idx)
        if b:
            cars.append({
                "index": idx,
                "label": f"Mashina #{idx + 1}",
                "status": "busy",
                "order_id": b.order_id,
                "reserved_from": b.reserved_from.isoformat(),
                "reserved_until": b.reserved_until.isoformat(),
                "minutes_left": max(0, int((b.reserved_until - moment).total_seconds() // 60)),
            })
        else:
            cars.append({
                "index": idx,
                "label": f"Mashina #{idx + 1}",
                "status": "available",
                "order_id": None,
                "reserved_from": None,
                "reserved_until": None,
                "minutes_left": 0,
            })

    busy_count = len(by_idx)
    next_free_at = None
    if busy_count >= car_count and active:
        next_free_at = min(b.reserved_until for b in active).isoformat()

    return {
        "restaurant_id": restaurant_id,
        "branch_id": branch_id,
        "total": car_count,
        "busy": busy_count,
        "available": max(0, car_count - busy_count),
        "as_of": moment.isoformat(),
        "next_free_at": next_free_at,
        "cars": cars,
    }


async def check_slot_availability(
    db: AsyncSession,
    *,
    restaurant_id: int,
    branch_id: int,
    slot_start: datetime,
    slot_end: datetime,
) -> bool:
    """Bitta vaqt-slot uchun bo'sh mashina bor-yo'qligi (filial darajasida)."""
    idx = await find_available_car(
        db, restaurant_id=restaurant_id, branch_id=branch_id,
        reserved_from=slot_start, reserved_until=slot_end,
    )
    return idx is not None
