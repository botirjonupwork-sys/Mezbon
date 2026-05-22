"""Yandex Delivery webhook handler.

Endpoint: GET /webhooks/yandex?claim_id=...&updated_ts=...&token=<secret>

Real Yandex API xulq-atvori (2026-05 da tekshirildi):
  - Yandex webhook **GET** so'rovi bilan keladi, body yo'q.
  - URL'ga `claim_id` va `updated_ts` query parametrlari append qilinadi.
  - Yandex faqat "ping" yuboradi — status va performer ma'lumotini olish uchun
    bizning kod alohida `/claims/info` ga so'rov yuborishi kerak.
  - Webhook signature mexanizmi yo'q. Xavfsizlik uchun callback_url da
    `?token=<secret>` qo'shilgan bo'lishi shart.
  - 200 javob qaytarish kerak; aks holda Yandex bir necha marta urinib,
    keyin tark etadi.

Yandex'ning to'liq status oqimi (26 ta):
  Asosiy:   new → estimating → ready_for_approval → accepted →
            performer_lookup → performer_draft → performer_found →
            pickup_arrived → ready_for_pickup_confirmation → pickuped →
            delivery_arrived → ready_for_delivery_confirmation →
            pay_waiting → delivered → delivered_finish

  Qaytarish: returning → return_arrived → ready_for_return_confirmation →
            returned → returned_finish

  Bekor:    cancelled, cancelled_by_taxi, cancelled_with_payment,
            cancelled_with_items_on_hands

  Xato:     estimating_failed, performer_not_found, failed
"""
from __future__ import annotations

import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from database.models import Order, OrderStatus, Restaurant, User
from api.services.yandex_delivery import YandexDeliveryClient, YandexDeliveryError


router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)


# ── Status mapping: Yandex → bizning OrderStatus ────────────────────────

_YANDEX_TO_ORDER_STATUS = {
    "new":                              None,
    "estimating":                       None,
    "estimating_failed":                OrderStatus.cancelled,
    "ready_for_approval":               None,
    "accepted":                         OrderStatus.preparing,
    "performer_lookup":                 OrderStatus.preparing,
    "performer_draft":                  OrderStatus.preparing,
    "performer_found":                  OrderStatus.preparing,
    "performer_not_found":              None,
    "pickup_arrived":                   OrderStatus.ready,
    "ready_for_pickup_confirmation":    OrderStatus.ready,
    "pickuped":                         OrderStatus.delivering,
    "delivery_arrived":                 OrderStatus.delivering,
    "ready_for_delivery_confirmation":  OrderStatus.delivering,
    "pay_waiting":                      OrderStatus.delivering,
    "delivered":                        OrderStatus.delivered,
    "delivered_finish":                 OrderStatus.delivered,
    "returning":                        None,
    "return_arrived":                   None,
    "ready_for_return_confirmation":    None,
    "returned":                         OrderStatus.cancelled,
    "returned_finish":                  OrderStatus.cancelled,
    "cancelled":                        OrderStatus.cancelled,
    "cancelled_by_taxi":                OrderStatus.cancelled,
    "cancelled_with_payment":           OrderStatus.cancelled,
    "cancelled_with_items_on_hands":    OrderStatus.cancelled,
    "failed":                           OrderStatus.cancelled,
}

# Mijozga ko'rinadigan xabar matnlari
_STATUS_USER_MESSAGE = {
    "performer_found":            "🚗 Kuryer topildi, restoranga ketmoqda",
    "pickup_arrived":             "📍 Kuryer restoranga yetib keldi",
    "pickuped":                   "📦 Buyurtmangiz yo'lda!",
    "delivery_arrived":           "🏠 Kuryer manzilga yetib keldi",
    "delivered":                  "✅ Buyurtmangiz yetkazib berildi! Yoqimli ishtahangiz uchun rahmat 🙏",
    "delivered_finish":           "✅ Buyurtmangiz yetkazib berildi! Yoqimli ishtahangiz uchun rahmat 🙏",
    "cancelled":                  "❌ Buyurtma bekor qilindi",
    "cancelled_by_taxi":          "❌ Kuryer xizmati buyurtmani bekor qildi",
    "cancelled_with_items_on_hands": "⚠️ Buyurtma bekor qilindi, lekin mahsulot kuryerda qoldi. Operator bog'lanadi",
    "performer_not_found":        "⏳ Hozir kuryer topilmadi. Qayta urinilmoqda...",
    "failed":                     "⚠️ Yetkazib berishda muammo. Operator siz bilan bog'lanadi",
}


def _check_webhook_auth(request: Request) -> None:
    """Webhook autentifikatsiyasi — callback_url dagi ?token=... bilan."""
    expected = os.getenv("YANDEX_WEBHOOK_SECRET", "").strip()
    if not expected:
        log.warning("YANDEX_WEBHOOK_SECRET env yo'q — webhook autentifikatsiyasi o'chiq")
        return

    token = request.query_params.get("token", "").strip()
    if token == expected:
        return

    raise HTTPException(401, "Webhook autentifikatsiya yaroqsiz")


async def _notify_customer(
    db: AsyncSession,
    order: Order,
    yandex_status: str,
    performer_info: Optional[dict] = None,
) -> None:
    """Mijozga Telegram bot orqali status haqida xabar."""
    user_text = _STATUS_USER_MESSAGE.get(yandex_status)
    if not user_text:
        return

    user = (await db.execute(select(User).where(User.id == order.user_id))).scalar_one_or_none()
    if not user or not user.telegram_id:
        return

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == order.restaurant_id)
    )).scalar_one_or_none()
    bot_token = (rest.bot_token if rest else "") or os.getenv("BOT_TOKEN", "")
    if not bot_token:
        return

    text = f"📦 <b>Buyurtma #{order.id}</b>\n\n{user_text}"
    if performer_info and yandex_status == "performer_found":
        name = performer_info.get("courier_name") or performer_info.get("name")
        phone = performer_info.get("phone")
        car_model = performer_info.get("car_model")
        car_number = performer_info.get("car_number")
        car_color = performer_info.get("car_color")
        if name:
            text += f"\n\n👤 Kuryer: {name}"
        if phone:
            text += f"\n📞 Tel: {phone}"
        if car_model or car_number:
            car_line = " ".join(filter(None, [car_color, car_model, car_number]))
            text += f"\n🚗 {car_line}"

    if order.yandex_tracking_url and yandex_status in ("performer_found", "pickuped"):
        text += f"\n\n📍 <a href='{order.yandex_tracking_url}'>Buyurtmani kuzatish</a>"

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": user.telegram_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
    except Exception as e:
        log.warning("Yandex webhook notify failed: %s", e)


async def _handle_webhook(claim_id: str, request: Request, db: AsyncSession) -> dict:
    """Ichki handler — GET va POST uchun umumiy."""
    if not claim_id:
        raise HTTPException(400, "claim_id yo'q")

    order = (await db.execute(
        select(Order).where(Order.yandex_claim_id == claim_id)
    )).scalar_one_or_none()

    if not order:
        log.warning("Yandex webhook: order topilmadi claim_id=%s", claim_id)
        return {"ok": True, "note": "order_not_found"}

    # Restoran tokeniga ulanib `/claims/info` orqali joriy holatni olamiz.
    # Webhook bizga statusni yubormaydi — uni alohida so'rab olishimiz kerak.
    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == order.restaurant_id)
    )).scalar_one_or_none()
    if not rest or not rest.yandex_api_token:
        log.warning("Yandex webhook: restaurant token topilmadi order=%s", order.id)
        return {"ok": True, "note": "no_token"}

    client = YandexDeliveryClient(
        api_token=rest.yandex_api_token,
        test_mode=bool(rest.yandex_test_mode),
    )

    try:
        info = await client.get_claim_info(claim_id)
    except YandexDeliveryError as e:
        log.error("Yandex claim_info xatosi: %s", e)
        # 200 qaytaramiz — qayta urinish foydasiz, lekin 5xx bersak Yandex retry qiladi
        return {"ok": True, "note": "info_fetch_failed"}

    new_status = (info.get("status") or "").strip()
    if not new_status:
        return {"ok": True, "note": "no_status"}

    # Idempotency: status o'zgarmagan bo'lsa qaytib chiqamiz
    if order.yandex_status == new_status:
        return {"ok": True, "note": "no_change"}

    prev_yandex_status = order.yandex_status
    order.yandex_status = new_status

    # Ichki OrderStatus ni yangilash
    mapped_status = _YANDEX_TO_ORDER_STATUS.get(new_status)
    if mapped_status and order.status != mapped_status:
        if order.status != OrderStatus.cancelled:
            order.status = mapped_status

    # Tracking URL — agar hali olinmagan bo'lsa, performer topilganda olamiz
    if new_status == "performer_found" and not order.yandex_tracking_url:
        try:
            link = await client.get_tracking_link(claim_id)
            if link:
                order.yandex_tracking_url = link
        except Exception as e:
            log.warning("Yandex tracking_link xatosi: %s", e)

    await db.commit()

    performer_info = info.get("performer_info") or {}
    await _notify_customer(db, order, new_status, performer_info)

    log.info(
        "Yandex webhook: order #%d %s → %s (mapped=%s)",
        order.id, prev_yandex_status, new_status, mapped_status,
    )

    return {"ok": True, "order_id": order.id, "status": new_status}


# ── Endpoint (GET — Yandex'ning haqiqiy xulqi) ───────────────────────────

@router.get("/yandex")
async def yandex_webhook_get(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Yandex Delivery webhook — GET so'rovi.

    Yandex kabinetda webhook URL:
      https://api.tursunboyev.com/webhooks/yandex?token=<YANDEX_WEBHOOK_SECRET>

    Yandex shu URL'ga `claim_id` va `updated_ts` query parametrlarini append qiladi.
    """
    _check_webhook_auth(request)
    claim_id = (request.query_params.get("claim_id") or "").strip()
    return await _handle_webhook(claim_id, request, db)


# ── Endpoint (POST — backward compatibility uchun saqlanadi) ─────────────

@router.post("/yandex")
async def yandex_webhook_post(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST fallback — agar Yandex kelajakda JSON body bilan POST qilsa.

    Query yoki JSON body'dagi claim_id ni qabul qiladi.
    """
    _check_webhook_auth(request)

    claim_id = (request.query_params.get("claim_id") or "").strip()
    if not claim_id:
        try:
            payload = await request.json()
            claim_id = (payload.get("claim_id") or payload.get("id") or "").strip()
        except Exception:
            pass

    return await _handle_webhook(claim_id, request, db)
