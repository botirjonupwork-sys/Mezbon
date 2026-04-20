"""Delivery provider orchestrator — restaurant sozlamasiga qarab provider tanlaydi."""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Restaurant, Branch, Order, OrderItem, Product, User
from api.services.yandex_delivery import YandexDeliveryClient, YandexDeliveryError


async def dispatch_order_to_provider(
    order: Order,
    db: AsyncSession,
) -> Optional[dict]:
    """Buyurtma tasdiqlanganda dastavka providerga yuborish.

    Qaytaradi: {provider, claim_id, tracking_url, price} yoki None (agar own kuryer)
    """
    if order.delivery_type.value != "delivery":
        return None

    # Restaurant sozlamalarini olish
    restaurant_id = order.restaurant_id
    if not restaurant_id and order.branch_id:
        br = await db.execute(select(Branch).where(Branch.id == order.branch_id))
        branch = br.scalar_one_or_none()
        if branch:
            restaurant_id = branch.restaurant_id

    if not restaurant_id:
        return None

    rest_res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    restaurant = rest_res.scalar_one_or_none()
    if not restaurant:
        return None

    provider = restaurant.delivery_provider or "own"
    if provider == "own":
        return None  # O'z kuryer — hech nima qilinmaydi

    if provider == "yandex":
        return await _dispatch_yandex(order, restaurant, db)

    return None


async def _dispatch_yandex(order: Order, restaurant: Restaurant, db: AsyncSession) -> dict:
    """Yandex Delivery ga claim yaratish."""
    # Pickup — branch yoki restaurant manzili
    pickup_lat = restaurant.restaurant_lat
    pickup_lon = restaurant.restaurant_lon
    pickup_address = restaurant.address or ""
    pickup_phone = restaurant.phone or ""
    pickup_name = restaurant.name

    if order.branch_id:
        br = await db.execute(select(Branch).where(Branch.id == order.branch_id))
        branch = br.scalar_one_or_none()
        if branch and branch.latitude and branch.longitude:
            pickup_lat = branch.latitude
            pickup_lon = branch.longitude
            pickup_address = branch.address or pickup_address
            pickup_phone = branch.phone or pickup_phone

    # Dropoff — mijoz manzili
    user_res = await db.execute(select(User).where(User.id == order.user_id))
    user = user_res.scalar_one_or_none()
    dropoff_name = user.full_name if user else "Mijoz"
    dropoff_phone = user.phone if user else ""

    # Mahsulotlar ro'yxati
    items_res = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    order_items = items_res.scalars().all()
    items = []
    for oi in order_items:
        prod_res = await db.execute(select(Product).where(Product.id == oi.product_id))
        prod = prod_res.scalar_one_or_none()
        items.append({
            "title": prod.name_uz if prod else f"Mahsulot #{oi.product_id}",
            "quantity": oi.quantity,
            "cost_value": oi.price,
            "weight_kg": 0.5,
        })

    client = YandexDeliveryClient(
        api_token=restaurant.yandex_api_token or "",
        test_mode=bool(restaurant.yandex_test_mode),
    )

    try:
        result = await client.create_claim(
            pickup_address=pickup_address,
            pickup_lat=pickup_lat or 41.2995,
            pickup_lon=pickup_lon or 69.2401,
            pickup_phone=pickup_phone,
            pickup_name=pickup_name,
            dropoff_address=order.address or "",
            dropoff_lat=order.latitude or 41.2995,
            dropoff_lon=order.longitude or 69.2401,
            dropoff_phone=dropoff_phone,
            dropoff_name=dropoff_name,
            items=items,
            total_price=order.total_price,
            comment=order.comment,
        )
    except YandexDeliveryError as e:
        return {"provider": "yandex", "error": str(e)}

    # Order ga saqlash
    order.yandex_claim_id = result["id"]
    order.yandex_status = result.get("status")
    order.yandex_tracking_url = result.get("tracking_url")
    order.yandex_price = result.get("price")
    await db.commit()

    return {"provider": "yandex", **result}
