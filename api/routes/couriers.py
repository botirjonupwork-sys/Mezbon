import os
import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Header

load_dotenv()
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional

from api.database import get_db
from api.auth_deps import require_restaurant_admin
from database.models import Courier, CourierStatus, Order, OrderStatus, Branch

router = APIRouter(prefix="/couriers", tags=["couriers"])

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


async def _require_bot_secret(x_bot_secret: Optional[str] = Header(None, alias="X-Bot-Secret")):
    """Courier-bot↔API ichki auth — telegram_id spoofing'dan himoya (audit C3)."""
    from api.services.security import is_valid_bot_secret
    if not is_valid_bot_secret(x_bot_secret or ""):
        raise HTTPException(403, "Ruxsat berilmadi")
    return True


class CourierRegister(BaseModel):
    telegram_id: str
    full_name: str
    phone: str
    transport_type: str = "car"
    branch_id: Optional[int] = None


# ── Ro'yxatdan o'tish ──────────────────────────────────
@router.post("/register")
async def register_courier(data: CourierRegister, db: AsyncSession = Depends(get_db), _bot: bool = Depends(_require_bot_secret)):
    """Yangi kuryer ro'yxatdan o'tishi.

    SaaS izolatsiya: courier.restaurant_id branch.restaurant_id'dan olinadi.
    Branch ko'rsatilmasa — xato (kuryer qaysi restoranniki ekan bilolmaymiz).
    """
    result = await db.execute(
        select(Courier).where(Courier.telegram_id == data.telegram_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Siz allaqachon ro'yxatdan o'tgansiz!")

    # Branch'dan restaurant_id aniqlash (SaaS izolatsiya)
    if not data.branch_id:
        raise HTTPException(400, "branch_id majburiy — kuryer qaysi filialda ishlashini ko'rsating")

    branch = (await db.execute(
        select(Branch).where(Branch.id == data.branch_id, Branch.is_active == True)
    )).scalar_one_or_none()
    if not branch:
        raise HTTPException(404, "Filial topilmadi")

    courier = Courier(
        telegram_id=data.telegram_id,
        full_name=data.full_name,
        phone=data.phone,
        transport_type=data.transport_type,
        branch_id=data.branch_id,
        restaurant_id=branch.restaurant_id,  # SaaS izolatsiya
    )
    db.add(courier)
    await db.commit()
    return {"status": "ok", "message": "Ariza qabul qilindi"}


# ── Kuryer ma'lumotlari ────────────────────────────────
@router.get("/{telegram_id}")
async def get_courier(telegram_id: str, db: AsyncSession = Depends(get_db), _bot: bool = Depends(_require_bot_secret)):
    result = await db.execute(
        select(Courier).where(Courier.telegram_id == telegram_id)
    )
    courier = result.scalar_one_or_none()
    if not courier:
        raise HTTPException(404, "Kuryer topilmadi")
    return {
        "id": courier.id,
        "telegram_id": courier.telegram_id,
        "full_name": courier.full_name,
        "phone": courier.phone,
        "transport_type": courier.transport_type,
        "status": courier.status.value,
    }


# ── Kuryerning faol zakazlari ──────────────────────────
@router.get("/{telegram_id}/orders")
async def courier_orders(telegram_id: str, db: AsyncSession = Depends(get_db), _bot: bool = Depends(_require_bot_secret)):
    result = await db.execute(
        select(Courier).where(Courier.telegram_id == telegram_id)
    )
    courier = result.scalar_one_or_none()
    if not courier:
        raise HTTPException(404, "Kuryer topilmadi")

    result = await db.execute(
        select(Order)
        .where(Order.courier_id == courier.id)
        .where(Order.status.in_([OrderStatus.ready, OrderStatus.delivering]))
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()
    return [
        {
            "id": o.id,
            "address": o.address,
            "latitude": o.latitude,
            "longitude": o.longitude,
            "total_price": o.total_price,
            "status": o.status.value,
            "comment": o.comment,
        }
        for o in orders
    ]


# ── Statistika ─────────────────────────────────────────
@router.get("/{telegram_id}/stats")
async def courier_stats(telegram_id: str, db: AsyncSession = Depends(get_db), _bot: bool = Depends(_require_bot_secret)):
    result = await db.execute(
        select(Courier).where(Courier.telegram_id == telegram_id)
    )
    courier = result.scalar_one_or_none()
    if not courier:
        raise HTTPException(404, "Kuryer topilmadi")

    # Yetkazilganlar
    delivered = await db.execute(
        select(Order)
        .where(Order.courier_id == courier.id)
        .where(Order.status == OrderStatus.delivered)
    )
    total_delivered = len(delivered.scalars().all())

    # Faol
    active = await db.execute(
        select(Order)
        .where(Order.courier_id == courier.id)
        .where(Order.status.in_([OrderStatus.ready, OrderStatus.delivering]))
    )
    active_orders = len(active.scalars().all())

    return {"total_delivered": total_delivered, "active_orders": active_orders}


# ── Zakazni qabul qilish ──────────────────────────────
@router.post("/{telegram_id}/accept/{order_id}")
async def accept_order(telegram_id: str, order_id: int, db: AsyncSession = Depends(get_db), _bot: bool = Depends(_require_bot_secret)):
    result = await db.execute(
        select(Courier).where(Courier.telegram_id == telegram_id)
    )
    courier = result.scalar_one_or_none()
    if not courier or courier.status != CourierStatus.active:
        raise HTTPException(403, "Siz faol kuryer emassiz!")

    result = await db.execute(
        select(Order).options(selectinload(Order.user)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Zakaz topilmadi")

    # SaaS izolatsiya: kuryer faqat o'z restoraniining buyurtmalarini qabul qila oladi
    if courier.restaurant_id and order.restaurant_id and courier.restaurant_id != order.restaurant_id:
        raise HTTPException(403, "Bu zakaz boshqa restoranniki!")

    if order.courier_id and order.courier_id != courier.id:
        raise HTTPException(400, "Bu zakaz boshqa kuryerga tayinlangan!")

    # Status transition validatsiya — faqat ma'lum holatlarda accept mumkin
    valid_prev = (OrderStatus.confirmed, OrderStatus.preparing, OrderStatus.ready)
    if order.status not in valid_prev:
        raise HTTPException(400, f"Bu zakaz holatida ({order.status.value}) qabul qilib bo'lmaydi")

    order.courier_id = courier.id
    order.status = OrderStatus.delivering
    await db.commit()

    # Mijozga xabar
    await _notify_user(order, "🚗 Kuryeringiz yo'lga chiqdi! Tez orada yetkazamiz.")

    return {
        "id": order.id,
        "address": order.address,
        "latitude": order.latitude,
        "longitude": order.longitude,
        "total_price": order.total_price,
        "status": order.status.value,
    }


# ── Yetkazildi ─────────────────────────────────────────
@router.post("/{telegram_id}/delivered/{order_id}")
async def mark_delivered(telegram_id: str, order_id: int, db: AsyncSession = Depends(get_db), _bot: bool = Depends(_require_bot_secret)):
    result = await db.execute(
        select(Courier).where(Courier.telegram_id == telegram_id)
    )
    courier = result.scalar_one_or_none()
    if not courier:
        raise HTTPException(404, "Kuryer topilmadi")

    result = await db.execute(
        select(Order).options(selectinload(Order.user)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order or order.courier_id != courier.id:
        raise HTTPException(403, "Bu sizning zakazingiz emas!")

    order.status = OrderStatus.delivered
    await db.commit()

    # Mijozga xabar + avtomatik baholash tugmalari
    await _notify_user(
        order,
        f"📦 <b>Zakaz #{order.id}</b>\n\n"
        f"✅ Zakazingiz yetkazildi! Ishtahangiz chog' bo'lsin! 🥟\n\n"
        f"⭐ Buyurtmani baholang:",
        reply_markup={"inline_keyboard": [[
            {"text": "⭐", "callback_data": f"rate_order:{order.id}:1"},
            {"text": "⭐⭐", "callback_data": f"rate_order:{order.id}:2"},
            {"text": "⭐⭐⭐", "callback_data": f"rate_order:{order.id}:3"},
            {"text": "⭐⭐⭐⭐", "callback_data": f"rate_order:{order.id}:4"},
            {"text": "⭐⭐⭐⭐⭐", "callback_data": f"rate_order:{order.id}:5"},
        ]]},
    )

    return {"status": "ok"}


# ── Admin: barcha kuryerlar ────────────────────────────
@router.get("/")
async def list_couriers(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Courier).order_by(Courier.created_at.desc())

    # SaaS izolatsiya: restoran filteri har doim
    if restaurant_id is None:
        return []
    branch_ids_subq = select(Branch.id).where(Branch.restaurant_id == restaurant_id)
    query = query.where(Courier.branch_id.in_(branch_ids_subq))

    if branch_id:
        # IDOR
        br = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if not br or br.restaurant_id != restaurant_id:
            return []
        query = query.where(Courier.branch_id == branch_id)
    result = await db.execute(query)
    couriers = result.scalars().all()
    return [
        {
            "id": c.id,
            "telegram_id": c.telegram_id,
            "full_name": c.full_name,
            "phone": c.phone,
            "transport_type": c.transport_type,
            "status": c.status.value,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "branch_id": c.branch_id,
        }
        for c in couriers
    ]


class CourierUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    transport_type: Optional[str] = None


# ── Admin: kuryer ma'lumotlarini yangilash ─────────────
async def _check_courier_belongs(db, courier, restaurant_id) -> None:
    """IDOR himoyasi: kuryer joriy restoranniki ekanini tekshirish."""
    if not restaurant_id:
        return  # super-admin
    if not courier.branch_id:
        return  # restaurant-level kuryer
    br = (await db.execute(select(Branch).where(Branch.id == courier.branch_id))).scalar_one_or_none()
    if not br or br.restaurant_id != restaurant_id:
        raise HTTPException(403, "Bu kuryer sizning restoraningizniki emas")


@router.put("/{courier_id}")
async def update_courier(
    courier_id: int,
    data: CourierUpdate,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        raise HTTPException(404, "Kuryer topilmadi")
    await _check_courier_belongs(db, courier, restaurant_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(courier, key, value)
    await db.commit()
    return {"success": True}


# ── Admin: kuryerni o'chirish ──────────────────────────
@router.delete("/{courier_id}")
async def delete_courier(
    courier_id: int,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        raise HTTPException(404, "Kuryer topilmadi")
    await _check_courier_belongs(db, courier, restaurant_id)
    await db.delete(courier)
    await db.commit()
    return {"success": True}


# ── Admin: kuryer statusini o'zgartirish ───────────────
@router.patch("/{courier_id}/status")
async def update_courier_status(
    courier_id: int,
    status: str,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        raise HTTPException(404, "Kuryer topilmadi")
    await _check_courier_belongs(db, courier, restaurant_id)

    try:
        courier.status = CourierStatus(status)
    except ValueError:
        raise HTTPException(400, f"Noto'g'ri status: {status}")

    await db.commit()

    # Kuryerga xabar yuborish
    if status == "active":
        await _notify_courier(
            courier.telegram_id,
            "✅ Tabriklaymiz! Sizning arizangiz tasdiqlandi.\n"
            "Endi sizga zakazlar keladi!",
        )
    elif status == "blocked":
        await _notify_courier(
            courier.telegram_id,
            "🚫 Sizning hisobingiz bloklandi.\nAdmin bilan bog'laning.",
        )

    return {"status": "ok"}


async def _notify_user(order, text: str, reply_markup: dict = None):
    """Mijozga Telegram orqali xabar yuborish."""
    bot_token = os.getenv("BOT_TOKEN", "")
    print(f"[Couriers] _notify_user: bot_token={'set' if bot_token else 'NOT SET'}, user={getattr(order, 'user', None)}")
    if not bot_token or not order.user:
        print(f"[Couriers] _notify_user skipped: token={bool(bot_token)}, user={bool(order.user)}")
        return
    payload = {
        "chat_id": order.user.telegram_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=payload,
                timeout=5.0,
            )
            print(f"[Couriers] _notify_user to {order.user.telegram_id}: {r.status_code}")
    except Exception as e:
        print(f"[Couriers] _notify_user error: {e}")


async def _notify_courier(telegram_id: str, text: str):
    """Kuryerga kuryer boti orqali xabar yuborish."""
    courier_token = os.getenv("COURIER_BOT_TOKEN", "")
    if not courier_token:
        print("[Courier] COURIER_BOT_TOKEN not set!")
        return
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://api.telegram.org/bot{courier_token}/sendMessage",
                json={
                    "chat_id": telegram_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
                timeout=5.0,
            )
            print(f"[Courier] Notify {telegram_id}: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"[Courier] Notify error: {e}")
