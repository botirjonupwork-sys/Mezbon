"""Delivery provider orchestrator — restaurant sozlamasiga qarab provider tanlaydi."""
import os
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Restaurant, Branch, Order, OrderItem, Product, User
from api.services.yandex_delivery import YandexDeliveryClient, YandexDeliveryError
from api.auth_deps import get_restaurant_plan, restaurant_has_feature

log = logging.getLogger(__name__)


def _build_callback_url() -> Optional[str]:
    """Yandex webhook callback URL'ini sozlamadan tuzish.

    Format: https://<API_DOMAIN>/webhooks/yandex?token=<SECRET>
    Yandex bu URL'ga `&claim_id=...&updated_ts=...` ni append qiladi.
    `?` belgisi bo'lishi shart (Yandex faqat append qiladi).
    """
    api_domain = os.getenv("API_PUBLIC_URL", "").rstrip("/")
    secret = os.getenv("YANDEX_WEBHOOK_SECRET", "").strip()
    if not api_domain or not secret:
        return None
    return f"{api_domain}/webhooks/yandex?token={secret}"


async def dispatch_order_to_provider(
    order: Order,
    db: AsyncSession,
) -> Optional[dict]:
    """Buyurtma tasdiqlanganda dastavka providerga yuborish.

    Qaytaradi: {provider, claim_id, tracking_url, price} yoki None (agar own kuryer)
    """
    if order.delivery_type.value != "delivery":
        return None

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
        return None

    if provider == "yandex":
        plan = await get_restaurant_plan(restaurant_id, db)
        if not restaurant_has_feature(plan, "yandex"):
            log.info("[delivery] Yandex feature joriy tarifda yo'q (restaurant_id=%s); 'own' ga fallback", restaurant_id)
            return None
        return await _dispatch_yandex(order, restaurant, db)

    return None


async def _dispatch_yandex(order: Order, restaurant: Restaurant, db: AsyncSession) -> dict:
    """Yandex Delivery ga claim yaratish + darhol accept qilish."""
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

    user_res = await db.execute(select(User).where(User.id == order.user_id))
    user = user_res.scalar_one_or_none()
    dropoff_name = user.full_name if user else "Mijoz"
    dropoff_phone = user.phone if user else ""

    # Mahsulotlar
    items_res = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    order_items = items_res.scalars().all()
    items = []
    for oi in order_items:
        prod_res = await db.execute(select(Product).where(Product.id == oi.product_id))
        prod = prod_res.scalar_one_or_none()
        items.append({
            "title": (prod.name_uz if prod else f"Mahsulot #{oi.product_id}")[:60],
            "quantity": oi.quantity,
            "cost_value": oi.price,
            "weight_kg": 0.5,  # default — kelajakda product.weight ga ko'chirish mumkin
        })

    client = YandexDeliveryClient(
        api_token=restaurant.yandex_api_token or "",
        test_mode=bool(restaurant.yandex_test_mode),
    )

    callback_url = _build_callback_url()

    try:
        create_result = await client.create_claim(
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
            callback_url=callback_url,
            emergency_phone=pickup_phone,
        )
    except YandexDeliveryError as e:
        log.error("Yandex create_claim xato: %s", e)
        return {"provider": "yandex", "error": str(e)}

    claim_id = create_result["id"]
    version = create_result.get("version", 1)

    # Darhol accept qilish — offer 10 daqiqada eskiradi
    try:
        accept_result = await client.accept_claim(claim_id, version=version)
        accepted_status = accept_result.get("status") or create_result["status"]
    except YandexDeliveryError as e:
        log.warning("Yandex accept_claim xato (create ok): %s", e)
        accepted_status = create_result["status"]

    # Tracking URL — alohida endpoint orqali
    tracking_url = None
    try:
        tracking_url = await client.get_tracking_link(claim_id)
    except Exception as e:
        log.warning("Yandex tracking_link xato: %s", e)

    # Order ga saqlash
    order.yandex_claim_id = claim_id
    order.yandex_status = accepted_status
    order.yandex_tracking_url = tracking_url
    order.yandex_price = create_result.get("price")
    await db.commit()

    return {
        "provider": "yandex",
        "id": claim_id,
        "status": accepted_status,
        "tracking_url": tracking_url,
        "price": create_result.get("price"),
    }
