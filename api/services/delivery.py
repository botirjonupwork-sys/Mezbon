"""Delivery provider orchestrator — restaurant sozlamasiga qarab provider tanlaydi.

Vaqtli (scheduled) Yandex zakaz:
  * `due` — kuryerning restoran (A) ga kelish vaqti
  * Uzoq kelajakdagi slotlar uchun claim yaratish kechiktiriladi
    (scheduler ~LEAD daqiqa oldin yuboradi)
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Restaurant, Branch, Order, OrderItem, Product, User
from api.services.yandex_delivery import YandexDeliveryClient, YandexDeliveryError
from api.auth_deps import get_restaurant_plan, restaurant_has_feature

log = logging.getLogger(__name__)

UZ_TZ = ZoneInfo("Asia/Tashkent")

# Mijoz tanlagan yetkazish vaqtidan shuncha daqiqa OLDIN kuryer restoranga keladi
YANDEX_PICKUP_BEFORE_DELIVERY_MIN = 25
# Shu vaqtdan uzoqroq slotlar uchun claim yaratishni kechiktiramiz
YANDEX_SCHEDULE_LEAD_MINUTES = 45


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


def _as_utc(dt: datetime) -> datetime:
    """Naive datetime ni UTC deb qabul qilish (DB'da UTC saqlanadi)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def yandex_due_iso_for_order(order: Order, *, now: Optional[datetime] = None) -> Optional[str]:
    """Order.scheduled_for dan Yandex `due` (ISO 8601, UTC) hisoblash.

    due = yetkazish vaqti − PICKUP_BEFORE (kuryer restoranga erta keladi).
    Juda yaqin bo'lsa — None (darhol qidirish).
    """
    if not order.scheduled_for:
        return None
    now_utc = _as_utc(now or datetime.utcnow())
    delivery_at = _as_utc(order.scheduled_for)
    due_at = delivery_at - timedelta(minutes=YANDEX_PICKUP_BEFORE_DELIVERY_MIN)
    # Minimal: hozirdan 5 daqiqa keyin (o'tgan due yubormaslik)
    min_due = now_utc + timedelta(minutes=5)
    if due_at < min_due:
        # Slot allaqachon yaqin — due shart emas (ASAP)
        if delivery_at <= now_utc + timedelta(minutes=15):
            return None
        due_at = min_due
    return due_at.isoformat().replace("+00:00", "Z")


def should_defer_yandex_dispatch(order: Order, *, now: Optional[datetime] = None) -> bool:
    """Uzoq kelajakdagi slot — claim'ni hozir yaratmaslik kerakmi?"""
    if not order.scheduled_for:
        return False
    if (order.delivery_time_slot or "").strip().lower() in ("", "now"):
        return False
    now_utc = _as_utc(now or datetime.utcnow())
    delivery_at = _as_utc(order.scheduled_for)
    # LEAD daqiqadan uzoqroq → kechiktiramiz
    return delivery_at > now_utc + timedelta(minutes=YANDEX_SCHEDULE_LEAD_MINUTES)


async def dispatch_order_to_provider(
    order: Order,
    db: AsyncSession,
    *,
    force: bool = False,
) -> Optional[dict]:
    """Buyurtma tasdiqlanganda dastavka providerga yuborish.

    force=True — scheduler vaqtli zakazni yuborayotganda (defer e'tiborsiz).

    Qaytaradi: {provider, claim_id, tracking_url, price} yoki None (agar own kuryer)
    """
    if order.delivery_type.value != "delivery":
        return None

    # Allaqachon claim bor — takrorlamaymiz
    if order.yandex_claim_id:
        return {
            "provider": "yandex",
            "id": order.yandex_claim_id,
            "status": order.yandex_status,
            "already_dispatched": True,
        }

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

        # Vaqtli zakaz — hali erta: keyinroq scheduler yuboradi
        if not force and should_defer_yandex_dispatch(order):
            order.yandex_status = "scheduled_pending"
            await db.commit()
            due_preview = yandex_due_iso_for_order(order)
            log.info(
                "[delivery] Yandex claim kechiktirildi (order=#%s, scheduled_for=%s, due≈%s)",
                order.id, order.scheduled_for, due_preview,
            )
            return {
                "provider": "yandex",
                "status": "scheduled_pending",
                "scheduled_for": order.scheduled_for.isoformat() if order.scheduled_for else None,
                "due": due_preview,
                "deferred": True,
            }

        balance_guard = await _check_yandex_balance_before_dispatch(restaurant, order, db)
        if balance_guard:
            return balance_guard
        return await _dispatch_yandex(order, restaurant, db)

    return None


async def _check_yandex_balance_before_dispatch(
    restaurant: Restaurant,
    order: Order,
    db: AsyncSession,
) -> Optional[dict]:
    """Critical balansda Yandex claim yaratishdan oldin himoya."""
    if not restaurant.yandex_balance_monitor_enabled:
        return None

    from api.services.yandex_balance import check_restaurant_yandex_balance

    snapshot = await check_restaurant_yandex_balance(db, restaurant, notify=True)
    if snapshot.get("status") != "critical":
        return None

    if not restaurant.yandex_balance_block_on_critical:
        log.warning(
            "[delivery] Yandex balance critical, but block disabled; continuing (restaurant_id=%s, order_id=%s)",
            restaurant.id,
            order.id,
        )
        return None

    order.yandex_status = "blocked_balance_critical"
    await db.commit()
    log.warning(
        "[delivery] Yandex dispatch blocked by critical balance (restaurant_id=%s, order_id=%s)",
        restaurant.id,
        order.id,
    )
    return {
        "provider": "yandex",
        "error": "yandex_balance_critical",
        "status": "blocked_balance_critical",
        "balance": snapshot,
    }


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
            # Placeholder Toshkent markazi — restoran koordinatasini afzal ko'ramiz
            is_placeholder = (
                abs(float(branch.latitude) - 41.2995) < 0.0002
                and abs(float(branch.longitude) - 69.2401) < 0.0002
            )
            if not is_placeholder:
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
            "weight_kg": 0.5,
        })

    client = YandexDeliveryClient(
        api_token=restaurant.yandex_api_token or "",
        test_mode=bool(restaurant.yandex_test_mode),
    )

    callback_url = _build_callback_url()
    due = yandex_due_iso_for_order(order)

    # Commentga vaqt belgisini qo'shamiz (kuryer/oshxona uchun)
    comment = order.comment or ""
    if order.scheduled_for and (order.delivery_time_slot or "") not in ("", "now"):
        try:
            local = _as_utc(order.scheduled_for).astimezone(UZ_TZ)
            slot_note = f"Yetkazish vaqti: {local.strftime('%H:%M')} ({local.strftime('%d.%m.%Y')})"
            comment = f"{slot_note}. {comment}".strip()
        except Exception:
            pass

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
            comment=comment,
            callback_url=callback_url,
            emergency_phone=pickup_phone,
            due=due,
        )
    except YandexDeliveryError as e:
        log.error("Yandex create_claim xato: %s", e)
        # due rad etilsa — due'siz qayta urinish
        if due and "due" in str(e).lower():
            log.warning("Yandex due rad etildi — ASAP qayta urinilmoqda (order=#%s)", order.id)
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
                    comment=comment,
                    callback_url=callback_url,
                    emergency_phone=pickup_phone,
                    due=None,
                )
            except YandexDeliveryError as e2:
                return {"provider": "yandex", "error": str(e2)}
        else:
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

    tracking_url = None
    try:
        tracking_url = await client.get_tracking_link(claim_id)
    except Exception as e:
        log.warning("Yandex tracking_link xato: %s", e)

    order.yandex_claim_id = claim_id
    order.yandex_status = accepted_status
    order.yandex_tracking_url = tracking_url
    order.yandex_price = create_result.get("price")
    await db.commit()

    log.info(
        "[delivery] Yandex claim yaratildi order=#%s claim=%s due=%s",
        order.id, claim_id, due,
    )

    return {
        "provider": "yandex",
        "id": claim_id,
        "status": accepted_status,
        "tracking_url": tracking_url,
        "price": create_result.get("price"),
        "due": due,
    }


async def dispatch_due_scheduled_yandex_orders(db: AsyncSession) -> dict:
    """Scheduler: to'langan, vaqti yaqinlashgan, hali claim yo'q zakazlarni yuborish."""
    from database.models import DeliveryType, OrderStatus

    now = datetime.utcnow()
    horizon = now + timedelta(minutes=YANDEX_SCHEDULE_LEAD_MINUTES + 5)

    res = await db.execute(
        select(Order).where(
            Order.delivery_type == DeliveryType.delivery,
            Order.payment_status == "paid",
            Order.yandex_claim_id.is_(None),
            Order.scheduled_for.isnot(None),
            Order.scheduled_for <= horizon,
            Order.status.notin_([OrderStatus.cancelled, OrderStatus.delivered]),
        )
    )
    orders = list(res.scalars().all())
    sent = 0
    errors = 0
    for order in orders:
        # Faqat deferred yoki hali yuborilmaganlar
        st = (order.yandex_status or "").lower()
        if st in ("blocked_balance_critical",):
            continue
        try:
            result = await dispatch_order_to_provider(order, db, force=True)
            if result and result.get("id"):
                sent += 1
            elif result and result.get("error"):
                errors += 1
        except Exception as e:
            errors += 1
            log.warning("Scheduled Yandex dispatch order=#%s xato: %s", order.id, e)

    return {"checked": len(orders), "sent": sent, "errors": errors}
