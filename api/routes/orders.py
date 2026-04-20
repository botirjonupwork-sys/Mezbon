import os
import httpx
from dotenv import load_dotenv
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

load_dotenv()
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from api.database import get_db
from api.schemas import OrderCreate, OrderOut
from api.config import settings
from database.models import Order, OrderItem, OrderStatus, Product, User, Courier, CourierStatus, Branch, Restaurant
from pos.alice import alice_pos
from api.services.delivery import dispatch_order_to_provider

STATUS_MSG = {
    "confirmed":  "✅ Zakazingiz qabul qilindi! Tayyorlanishni boshlaymiz.",
    "preparing":  "👨‍🍳 Zakazingiz tayyorlanmoqda...",
    "ready":      "📦 Zakazingiz tayyor! Kuryer tez orada jo'naydi.",
    "delivering": "🚗 Kuryeringiz yo'lda! Tez orada yetib keladi.",
    "delivered":  "✅ Zakazingiz yetkazildi! Ishtahangiz chog' bo'lsin! 🥟\n\n⭐ Bizni baholashni unutmang: /review",
    "cancelled":  "❌ Afsuski zakazingiz bekor qilindi. Boshqa savollarga javob berishga tayyormiz.",
}


async def _notify_user_status(telegram_id: str, order_id: int, status: str, restaurant_id: int = None, db: AsyncSession = None):
    """Mijozga Telegram orqali status xabari yuborish (API dan chaqiriladi)"""
    msg = STATUS_MSG.get(status)
    if not msg:
        return
    # Restoran bot tokenini aniqlash
    bot_token = os.getenv("BOT_TOKEN", "")
    if restaurant_id and db:
        try:
            result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
            rest = result.scalar_one_or_none()
            if rest and rest.bot_token:
                bot_token = rest.bot_token
        except Exception:
            pass
    if not bot_token:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": telegram_id,
                    "text": f"📦 <b>Zakaz #{order_id}</b>\n\n{msg}",
                    "parse_mode": "HTML",
                },
                timeout=5.0,
            )
    except Exception:
        pass

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/", response_model=OrderOut)
async def create_order(
    telegram_id: str,
    data: OrderCreate,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    # Foydalanuvchini topish
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    # Mahsulotlarni tekshirish va narx hisoblash
    total = 0.0
    order_items = []

    for item in data.items:
        result = await db.execute(select(Product).where(Product.id == item.product_id))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(404, f"Mahsulot #{item.product_id} topilmadi")
        if product.is_stop:
            raise HTTPException(400, f"'{product.name_uz}' hozir mavjud emas")

        item_price = product.price * item.quantity
        total += item_price
        order_items.append((product, item.quantity, product.price))

    if data.delivery_fee is not None:
        delivery_fee = data.delivery_fee
    else:
        delivery_fee = 0.0

    # branch_id dan restaurant_id aniqlash
    order_branch_id = data.branch_id
    order_restaurant_id = restaurant_id
    if order_branch_id and not order_restaurant_id:
        br = await db.execute(select(Branch).where(Branch.id == order_branch_id))
        branch = br.scalar_one_or_none()
        if branch:
            order_restaurant_id = branch.restaurant_id
    # Mahsulotdan aniqlash (fallback)
    if not order_restaurant_id and order_items:
        order_restaurant_id = order_items[0][0].restaurant_id

    # Zakaz yaratish
    order = Order(
        user_id=user.id,
        branch_id=order_branch_id,
        restaurant_id=order_restaurant_id,
        delivery_type=data.delivery_type,
        address=data.address,
        latitude=data.latitude,
        longitude=data.longitude,
        comment=data.comment,
        total_price=total,
        delivery_fee=delivery_fee,
        status=OrderStatus.pending,
    )
    db.add(order)
    await db.flush()

    for product, quantity, price in order_items:
        db.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            price=price,
        ))

    await db.commit()

    # Alice POS ga yuborish
    try:
        alice_order = await alice_pos.create_order({
            "items": [
                {"productId": p.alice_product_id, "quantity": q, "price": pr}
                for p, q, pr in order_items
            ],
            "customer_name": user.full_name,
            "customer_phone": user.phone,
            "comment": data.comment or "",
            "delivery_type": data.delivery_type.value,
        })
        order.alice_order_id = alice_order.get("id")
        await db.commit()
    except Exception:
        pass  # Alice POS xatosi butun zakazni to'xtatmasin

    # Dastavka provider — restaurant sozlamasiga qarab yuborish
    # "own" → o'z kuryerlari (bot orqali)
    # "yandex" → Yandex Delivery
    if data.delivery_type.value == "delivery":
        rest_res = await db.execute(select(Restaurant).where(Restaurant.id == order_restaurant_id))
        rest = rest_res.scalar_one_or_none()
        provider = (rest.delivery_provider if rest else "own") or "own"

        if provider == "yandex":
            try:
                await dispatch_order_to_provider(order, db)
            except Exception as e:
                print(f"[Yandex] Dispatch xato: {e}")
        else:
            # O'z kuryerlariga xabar yuborish
            await _notify_couriers_new_order(db, order, order_items, user)

    # items ni eager load qilib qaytarish
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    )
    return result.scalar_one()


@router.get("/user/{telegram_id}", response_model=list[OrderOut])
async def get_user_orders(telegram_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Zakaz topilmadi")
    return order


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: int,
    status: OrderStatus,
    db: AsyncSession = Depends(get_db)
):
    """Zakaz holatini yangilash (Admin uchun)"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Zakaz topilmadi")

    order.status = status
    await db.commit()

    # Mijozga Telegram xabar yuborish
    user_res = await db.execute(select(User).where(User.id == order.user_id))
    user = user_res.scalar_one_or_none()
    if user:
        await _notify_user_status(user.telegram_id, order_id, status.value, order.restaurant_id, db)

    # Zakaz tayyor bo'lganda ham kuryerlarga qayta xabar (faqat dastavka)
    if status == OrderStatus.ready and order.delivery_type.value == "delivery":
        print(f"[Orders] Re-notifying couriers: order #{order_id} is ready")
        await _notify_couriers_new_order(db, order)

    return {"success": True, "status": status}


async def _notify_couriers_new_order(db: AsyncSession, order: Order, order_items=None, user=None):
    """Barcha faol kuryerlarga yangi zakaz haqida xabar yuborish (kuryer bot orqali)."""
    courier_token = os.getenv("COURIER_BOT_TOKEN", "")
    print(f"[Courier] _notify_couriers_new_order called for order #{order.id}")
    print(f"[Courier] COURIER_BOT_TOKEN: {'set (' + courier_token[:10] + '...)' if courier_token else 'NOT SET!'}")
    if not courier_token:
        return

    result = await db.execute(
        select(Courier).where(Courier.status == CourierStatus.active)
    )
    couriers = result.scalars().all()
    if not couriers:
        print("[Courier] No active couriers found")
        return

    # Mahsulotlar ro'yxati
    items_text = ""
    if order_items:
        items_text = "\n".join(f"  • {p.name_uz} x{q}" for p, q, _ in order_items)

    # Mijoz ma'lumotlari
    user_info = ""
    if user:
        user_info = f"👤 Mijoz: {user.full_name}\n📞 Tel: {user.phone}\n"

    text = (
        f"🔔 <b>Yangi zakaz #{order.id}</b>\n\n"
        f"{user_info}"
        f"📍 Manzil: {order.address or '—'}\n"
        f"💰 Summa: {order.total_price:,.0f} so'm\n"
    )
    text += "💳 To'lov: 💵 Naqd\n"
    if order.delivery_fee:
        text += f"🚗 Dastavka: {order.delivery_fee:,.0f} so'm\n"
    if items_text:
        text += f"\n🛒 <b>Mahsulotlar:</b>\n{items_text}\n"
    if order.comment:
        text += f"\n💬 Izoh: {order.comment}\n"
    text += "\nQabul qilasizmi?"

    api_url = f"https://api.telegram.org/bot{courier_token}"

    for courier in couriers:
        try:
            async with httpx.AsyncClient() as client:
                # 1. Lokatsiya xaritasi AVVAL yuborilsin (kuryer darhol ko'rsin)
                if order.latitude and order.longitude:
                    loc_resp = await client.post(
                        f"{api_url}/sendLocation",
                        json={
                            "chat_id": courier.telegram_id,
                            "latitude": float(order.latitude),
                            "longitude": float(order.longitude),
                        },
                        timeout=5.0,
                    )
                    print(f"[Courier] Location sent to {courier.full_name}: {loc_resp.status_code}")

                # 2. Zakaz ma'lumotlari + tugmalar
                msg_resp = await client.post(
                    f"{api_url}/sendMessage",
                    json={
                        "chat_id": courier.telegram_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": {
                            "inline_keyboard": [[
                                {"text": "✅ Qabul qilish", "callback_data": f"accept:{order.id}"},
                                {"text": "❌ Rad etish", "callback_data": f"reject:{order.id}"},
                            ]]
                        },
                    },
                    timeout=5.0,
                )
                print(f"[Courier] Order #{order.id} sent to {courier.full_name}: {msg_resp.status_code}")
        except Exception as e:
            print(f"[Courier] Error notifying {courier.telegram_id}: {e}")
