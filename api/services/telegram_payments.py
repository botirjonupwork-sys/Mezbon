"""Telegram Native Payments — Click/Payme provider tokenlari orqali.

To'lov oqimi:
1. Mijoz "💳 To'lov" bosadi → bot `prepare_invoice()` chaqiradi (FastAPI)
2. Bot `bot.send_invoice()` orqali Telegram'ga LabeledPrice'lar yuboradi
3. Telegram → Click/Payme'ga ulayadi, mijoz to'lov qiladi
4. Telegram → bot ga `pre_checkout_query` yuboradi → bot `precheck_invoice()` chaqiradi
   (oxirgi marta resurs tekshiruv — mashina bandmi?)
5. Mijoz to'lov tasdiqlaydi → bot `successful_payment` oladi → `confirm_payment()` chaqiradi
   (status=paid, mashina band, komissiya yoziladi)

Tiyin matematikasi:
- Telegram `prices` da har LabeledPrice `amount` int — minimal birlik (UZS uchun tiyin)
- 1 so'm = 100 tiyin
- Hech qachon float ishlatmaymiz, faqat int(round(uzs * 100))

Provider tokenlari:
- Test: bot @BotFather'da "/setpaymentprovider" Click/Payme ni test rejimda ulanadi
- Prod: real merchant kalit Click/Payme dashboard'da generatsiya qilinadi
- Token formati: "<id>:TEST:<key>" (test) yoki "<id>:LIVE:<key>" (prod)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.logging_config import log_critical
from api.services.resources import (
    CarCapacityExceeded, book_car_for_order, find_available_car,
)
from database.models import (
    CommissionPayment, Order, OrderItem, OrderStatus, Plan, Product, Restaurant,
)


# ── Pul matematikasi ─────────────────────────────────────────────────────

def uzs_to_tiyin(uzs: float) -> int:
    """1 so'm = 100 tiyin. Float'ni xavfsiz int'ga aylantirish."""
    return int(round(float(uzs or 0) * 100))


def tiyin_to_uzs(tiyin: int) -> float:
    return (tiyin or 0) / 100.0


# ── Invoice schema ───────────────────────────────────────────────────────

@dataclass
class LabeledPriceItem:
    label: str
    amount_tiyin: int


@dataclass
class InvoicePayload:
    """`bot.send_invoice()` uchun barcha kerakli maydonlar."""
    order_id: int
    title: str
    description: str
    currency: str            # 'UZS'
    prices: list[LabeledPriceItem]
    payload: str             # Telegram payload (`order_<id>` formatda)
    provider_token: str
    total_tiyin: int
    is_prepayment: bool
    prepayment_percent: Optional[int]
    full_total_tiyin: int    # to'liq summa (prepayment bo'lsa ham)

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "title": self.title,
            "description": self.description,
            "currency": self.currency,
            "prices": [{"label": p.label, "amount": p.amount_tiyin} for p in self.prices],
            "payload": self.payload,
            "provider_token": self.provider_token,
            "total_tiyin": self.total_tiyin,
            "is_prepayment": self.is_prepayment,
            "prepayment_percent": self.prepayment_percent,
            "full_total_tiyin": self.full_total_tiyin,
        }


# ── Provider token resolver ──────────────────────────────────────────────

def _resolve_provider_token(restaurant: Restaurant, provider: str) -> Optional[str]:
    """Telegram provider tokenini restoran sozlamasidan oladi.

    SaaS izolatsiya: har restoran o'z tokenini DB'da saqlaydi.
    Env fallback faqat dev/lokal sinov uchun va birinchi restoran (id=1) uchun
    qo'llaniladi — production'da har restoran o'zining unique tokenini olishi shart.

    Tartib:
      1. Restaurant.telegram_provider_token_<click|payme> (admin UI)
      2. pos_config['telegram_provider_token_<click|payme>'] (backward-compat)
      3. Env: TELEGRAM_PROVIDER_TOKEN_<CLICK|PAYME> (faqat rest_id=1 uchun)
    """
    field = f"telegram_provider_token_{provider}"
    token = (getattr(restaurant, field, None) or "").strip()

    if not token:
        cfg = restaurant.pos_config or {}
        token = (cfg.get(field) or "").strip()

    # Env fallback faqat birinchi restoran uchun (lokal sinov)
    if not token and restaurant.id == 1:
        import os
        token = os.getenv(f"TELEGRAM_PROVIDER_TOKEN_{provider.upper()}", "").strip()
    return token or None


# ── Order summary builder ────────────────────────────────────────────────

@dataclass
class OrderPaymentSummary:
    items_total_uzs: float
    delivery_fee_uzs: float
    catering_service_fee_uzs: float
    grand_total_uzs: float
    is_prepayment: bool
    prepayment_percent: int
    prepayment_amount_uzs: float
    payable_now_uzs: float    # mijoz hozir to'laydigan summa


async def calculate_order_payment(
    db: AsyncSession,
    order: Order,
    restaurant: Restaurant,
) -> OrderPaymentSummary:
    """Buyurtma uchun to'lov tafsilotlari.

    Quyidagi qoidalar:
    1. items_total = order.total_price (Order.create paytida hisoblangan)
    2. delivery_fee = order.delivery_fee (Haversine bo'yicha hisoblangan)
    3. service_fee = restaurant.catering_service_fee (faqat onsite_catering uchun)
    4. grand_total = items + delivery + service
    5. Prepayment: agar restoran limiti belgilangan va grand >= limit bo'lsa,
       Plan.min_prepayment_percent foizi to'lanadi (faqat Basic/Pro tarifda)
    """
    items_total = float(order.total_price or 0)
    delivery_fee = float(order.delivery_fee or 0)

    service_fee = 0.0
    if (order.service_type or "").lower() == "onsite_catering":
        service_fee = float(restaurant.catering_service_fee or 0)

    grand = items_total + delivery_fee + service_fee

    # Prepayment qoidasi — 2 ta sabab:
    #   A. Buyurtma summasi `prepayment_required_above` chegarasidan oshsa
    #   B. (Faza 8) `enforce_prepayment_for_delivery` yoqilgan va
    #      delivery_subtype delivery yoki onsite catering bo'lsa
    is_prepayment = False
    prepayment_pct = 0
    prepayment_amount = 0.0

    plan = None
    if restaurant.plan_id:
        plan = (await db.execute(
            select(Plan).where(Plan.id == restaurant.plan_id)
        )).scalar_one_or_none()

    # Faza 8: yetkazib berish bo'yicha majburiy prepayment
    is_delivery_kind = (order.delivery_subtype or "").lower() in ("delivery", "onsite")
    enforce_for_delivery = bool(getattr(restaurant, "enforce_prepayment_for_delivery", False))

    # Sabab A: chegara
    limit = float(restaurant.prepayment_required_above or 0)
    triggered_by_amount = (limit > 0 and grand >= limit)

    # Sabab B: delivery enforce
    triggered_by_delivery = (enforce_for_delivery and is_delivery_kind)

    # Plan tarif — Basic/Pro'da prepayment foizi belgilangan
    plan_allows = (plan and plan.slug in ("basic", "pro", "free"))

    if plan_allows and (triggered_by_amount or triggered_by_delivery):
        prepayment_pct = max(0, min(100, int((plan and plan.min_prepayment_percent) or 30)))
        if prepayment_pct > 0:
            is_prepayment = True
            prepayment_amount = round(grand * prepayment_pct / 100.0, 0)

    payable_now = prepayment_amount if is_prepayment else grand

    return OrderPaymentSummary(
        items_total_uzs=items_total,
        delivery_fee_uzs=delivery_fee,
        catering_service_fee_uzs=service_fee,
        grand_total_uzs=grand,
        is_prepayment=is_prepayment,
        prepayment_percent=prepayment_pct,
        prepayment_amount_uzs=prepayment_amount,
        payable_now_uzs=payable_now,
    )


# ── Step 1: prepare invoice (FastAPI ↔ bot) ─────────────────────────────

async def prepare_invoice(
    db: AsyncSession,
    *,
    order_id: int,
    provider: str = "click",
) -> InvoicePayload:
    """Buyurtma uchun Telegram invoice payload tayyorlaydi.

    Raises:
        ValueError — order/restaurant topilmadi
        ProviderTokenMissing — Telegram provider token sozlanmagan
    """
    if provider not in ("click", "payme"):
        raise ValueError(f"Provider faqat 'click' yoki 'payme': {provider}")

    order = (await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )).scalar_one_or_none()
    if not order:
        raise ValueError(f"Order #{order_id} topilmadi")

    if order.payment_status == "paid":
        raise ValueError("Buyurtma allaqachon to'langan")

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == order.restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        raise ValueError("Restoran topilmadi")

    provider_token = _resolve_provider_token(rest, provider)
    if not provider_token:
        raise ProviderTokenMissing(
            f"Restaurant #{rest.id} uchun Telegram {provider} provider token sozlanmagan"
        )

    summary = await calculate_order_payment(db, order, rest)

    # Telegram LabeledPrice — har item alohida qator (foydalanuvchi ko'rsin)
    prices: list[LabeledPriceItem] = []
    if summary.is_prepayment:
        # Prepayment rejimida bitta qator yetadi — "Oldindan to'lov X%"
        prices.append(LabeledPriceItem(
            label=f"Oldindan to'lov ({summary.prepayment_percent}%)",
            amount_tiyin=uzs_to_tiyin(summary.prepayment_amount_uzs),
        ))
    elif order.is_catering or (order.order_kind or "") == "catering":
        # Catering — OrderItem.price USD'da bo'lishi mumkin (catering algoritm).
        # Aniq summa Order.total_price'da (so'm) saqlangan, undan foydalanamiz.
        prices.append(LabeledPriceItem(
            label=f"Catering buyurtma #{order.id} ({sum(i.quantity for i in order.items or [])} ta)",
            amount_tiyin=uzs_to_tiyin(summary.items_total_uzs),
        ))
        if summary.delivery_fee_uzs > 0:
            prices.append(LabeledPriceItem(
                label="Yetkazib berish", amount_tiyin=uzs_to_tiyin(summary.delivery_fee_uzs),
            ))
        if summary.catering_service_fee_uzs > 0:
            prices.append(LabeledPriceItem(
                label="Catering xizmat haqi",
                amount_tiyin=uzs_to_tiyin(summary.catering_service_fee_uzs),
            ))
    else:
        # Telegram limit: max ~10 LabeledPrice + label max 32 belgi va umumiy
        # payload ~4KB. Ko'p item bo'lsa "PRICE_LIST_TOO_LONG" xatosi keladi.
        # Shu uchun: 4 itemgacha alohida ko'rsatamiz, undan oshsa bitta
        # "Mahsulotlar (N ta)" qatoriga jamlaymiz.
        items_list = list(order.items or [])
        items_count = sum(i.quantity for i in items_list)
        AGGREGATE_THRESHOLD = 4

        if len(items_list) <= AGGREGATE_THRESHOLD:
            for item in items_list:
                prod = (await db.execute(
                    select(Product).where(Product.id == item.product_id)
                )).scalar_one_or_none()
                name = (prod.name_uz if prod else f"#{item.product_id}")[:24]
                prices.append(LabeledPriceItem(
                    label=f"{name} × {item.quantity}"[:32],
                    amount_tiyin=uzs_to_tiyin(item.price * item.quantity),
                ))
        else:
            prices.append(LabeledPriceItem(
                label=f"Mahsulotlar ({items_count} ta)"[:32],
                amount_tiyin=uzs_to_tiyin(summary.items_total_uzs),
            ))

        if summary.delivery_fee_uzs > 0:
            prices.append(LabeledPriceItem(
                label="Yetkazib berish", amount_tiyin=uzs_to_tiyin(summary.delivery_fee_uzs),
            ))
        if summary.catering_service_fee_uzs > 0:
            prices.append(LabeledPriceItem(
                label="Catering xizmat haqi",
                amount_tiyin=uzs_to_tiyin(summary.catering_service_fee_uzs),
            ))

    total_tiyin = sum(p.amount_tiyin for p in prices)

    # Telegram 0 summali invoice'ni rad etadi ("total price must be positive")
    if total_tiyin <= 0:
        raise ValueError(
            "Buyurtma summasi 0 — to'lov yaratib bo'lmaydi. "
            "Mahsulotlar narxi belgilanmagan bo'lishi mumkin."
        )

    title = f"Buyurtma #{order.id}"
    desc_parts = [f"{rest.name}"]
    if summary.is_prepayment:
        desc_parts.append(
            f"Jami: {int(summary.grand_total_uzs):,} so'm. "
            f"Oldindan {summary.prepayment_percent}% to'lov."
        )
    else:
        desc_parts.append(f"Jami: {int(summary.grand_total_uzs):,} so'm")

    return InvoicePayload(
        order_id=order.id,
        title=title,
        description=" ".join(desc_parts),
        currency="UZS",
        prices=prices,
        payload=f"order_{order.id}",
        provider_token=provider_token,
        total_tiyin=total_tiyin,
        is_prepayment=summary.is_prepayment,
        prepayment_percent=summary.prepayment_percent if summary.is_prepayment else None,
        full_total_tiyin=uzs_to_tiyin(summary.grand_total_uzs),
    )


class ProviderTokenMissing(Exception):
    pass


# ── Step 2: pre_checkout — oxirgi resurs tekshiruv ──────────────────────

@dataclass
class PrecheckResult:
    ok: bool
    error_message: Optional[str] = None
    reason_code: Optional[str] = None    # 'no_car' | 'order_not_found' | 'already_paid' | 'cancelled'


async def precheck_invoice(
    db: AsyncSession,
    *,
    order_id: int,
) -> PrecheckResult:
    """`pre_checkout_query` da chaqiriladi — to'lov o'tkazilishidan oldin
    oxirgi marta resurs (mashina) bormi tekshiradi.

    Mashina band bo'lib qolgan bo'lsa `ok=False` qaytaradi va Telegram bu
    bilan to'lovni rad etadi.
    """
    from datetime import datetime, timedelta

    order = (await db.execute(
        select(Order).where(Order.id == order_id)
    )).scalar_one_or_none()

    if not order:
        return PrecheckResult(False, "Buyurtma topilmadi", "order_not_found")
    if order.payment_status == "paid":
        return PrecheckResult(False, "Buyurtma allaqachon to'langan", "already_paid")
    if order.status == OrderStatus.cancelled:
        return PrecheckResult(False, "Buyurtma bekor qilingan", "cancelled")

    # Faqat dastavka uchun mashina kerak
    if order.delivery_type and order.delivery_type.value == "delivery":
        if not order.branch_id:
            # Restoranda umuman filial yo'q bo'lsa — bu OK, kuryer manual
            from sqlalchemy import select as _sel, func as _func
            from database.models import Branch as _Branch
            branch_count = (await db.execute(
                _sel(_func.count(_Branch.id)).where(
                    _Branch.restaurant_id == order.restaurant_id,
                    _Branch.is_active == True,
                )
            )).scalar() or 0
            if branch_count == 0:
                # Filiallar yo'q — mashina band qilish ham yo'q, OK
                return PrecheckResult(True)
            # Filiallar mavjud, lekin order'ga biriktirilmagan — bu xato
            log_critical(
                "payments", "Pre-checkout: order.branch_id yo'q (restoranda filiallar bor)",
                order_id=order.id, restaurant_id=order.restaurant_id,
            )
            return PrecheckResult(False, "Filial belgilanmagan", "no_branch")

        # SaaS IDOR: order.branch_id order.restaurant_id'ga tegishli bo'lishi shart
        from sqlalchemy import select as _sel
        from database.models import Branch as _Branch
        br_check = (await db.execute(
            _sel(_Branch).where(_Branch.id == order.branch_id)
        )).scalar_one_or_none()
        if br_check and br_check.restaurant_id != order.restaurant_id:
            log_critical(
                "payments", "Pre-checkout: branch boshqa restoraniki (cross-tenant)",
                order_id=order.id, order_rid=order.restaurant_id,
                branch_id=order.branch_id, branch_rid=br_check.restaurant_id,
            )
            return PrecheckResult(False, "Filial mos kelmaydi", "branch_mismatch")

        # 2 soatlik qisqa "soft hold" — slot mavjudligini hozir ham tekshiramiz
        now = datetime.utcnow()
        end = now + timedelta(hours=2)
        idx = await find_available_car(
            db,
            restaurant_id=order.restaurant_id,
            branch_id=order.branch_id,
            reserved_from=now,
            reserved_until=end,
        )
        if idx is None:
            return PrecheckResult(
                False,
                "Kechirasiz, mashinalarimiz to'liq band bo'lib qoldi. Keyinroq urinib ko'ring.",
                "no_car",
            )

    return PrecheckResult(True)


# ── Step 3: confirm payment + book car + record commission ──────────────

@dataclass
class ConfirmResult:
    ok: bool
    order_id: int
    paid_amount_tiyin: int
    booking_id: Optional[int]
    commission_id: Optional[int]
    error: Optional[str] = None
    # Faza 6: fiskal va VAT
    vat_amount_tiyin: int = 0
    fiscal_qr: Optional[str] = None


async def confirm_payment(
    db: AsyncSession,
    *,
    order_id: int,
    amount_tiyin: int,
    provider: str,
    telegram_payment_charge_id: Optional[str],
    provider_payment_charge_id: Optional[str],
    is_prepayment: bool = False,
    prepayment_percent: Optional[int] = None,
) -> ConfirmResult:
    """`successful_payment` handlerda chaqiriladi.

    Bajaradi:
        1. Order.payment_status = 'paid' (yoki 'partial' agar prepayment)
        2. Order.status = OrderStatus.confirmed (POS dispatch ishga tushadi)
        3. book_car_for_order() — mashina rasman band qilinadi
        4. CommissionPayment yozuvi (super-admin moliyaviy hisobi)

    Idempotent: agar shu `payment_charge_id` allaqachon yozilgan bo'lsa,
    funksiya 200 + mavjud yozuvni qaytaradi (Telegram bir xil event ikki marta
    yuborishi mumkin).
    """
    # Idempotency tekshiruvlar (2 ta):
    # 1. Charge ID bo'yicha (Telegram bir xil event ikki marta yuborishi mumkin)
    if telegram_payment_charge_id:
        existing = (await db.execute(
            select(Order).where(Order.payment_charge_id == telegram_payment_charge_id)
        )).scalar_one_or_none()
        if existing:
            return ConfirmResult(
                ok=True, order_id=existing.id,
                paid_amount_tiyin=existing.paid_amount_tiyin or 0,
                booking_id=None, commission_id=None,
                error="duplicate_event_already_processed",
            )

    order = (await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )).scalar_one_or_none()
    if not order:
        return ConfirmResult(False, order_id, 0, None, None, "order_not_found")

    # 2. Order'ning o'zi allaqachon to'langan bo'lsa — qayta to'lov rad etiladi
    if order.payment_status == "paid":
        return ConfirmResult(
            ok=True, order_id=order.id,
            paid_amount_tiyin=order.paid_amount_tiyin or 0,
            booking_id=None, commission_id=None,
            error="order_already_paid",
        )

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == order.restaurant_id)
    )).scalar_one_or_none()

    # 1. Order yangilash
    order.payment_status = "partial" if is_prepayment else "paid"
    order.payment_method = "telegram"
    order.payment_provider = provider
    order.payment_charge_id = telegram_payment_charge_id
    order.paid_amount_tiyin = (order.paid_amount_tiyin or 0) + amount_tiyin
    order.is_prepayment = is_prepayment
    order.prepayment_percent = prepayment_percent
    # Faza 6: VAT hisob — agar restoran QQS to'lovchi bo'lsa, total ichidagi QQS qismi
    # Formula: VAT = total * vat_pct / (100 + vat_pct)  (gross-from-net)
    if rest and rest.is_vat_payer and (rest.vat_percent or 0) > 0:
        vat_pct = float(rest.vat_percent)
        order.vat_amount_tiyin = int(round(amount_tiyin * vat_pct / (100 + vat_pct)))
    if order.status == OrderStatus.pending:
        order.status = OrderStatus.confirmed
    await db.commit()

    # 2. Mashina band qilish (faqat delivery + branch bor bo'lsa)
    booking = None
    booking_id = None
    if order.delivery_type and order.delivery_type.value == "delivery" and order.branch_id:
        try:
            booking = await book_car_for_order(
                db, order=order,
                is_catering=bool(order.is_catering),
                event_date=order.event_date,
            )
            booking_id = booking.id if booking else None
        except CarCapacityExceeded as e:
            log_critical(
                "payments", "Mashina band qilib bo'lmadi (post-payment)",
                order_id=order.id, restaurant_id=order.restaurant_id,
                error=str(e),
            )
            # To'lov tushdi, lekin mashina band qilinmadi — manual handling

    # 3. Komissiya yozuvi (super-admin moliyaviy hisobi)
    commission_id = None
    commission_uzs = 0.0
    paid_uzs = tiyin_to_uzs(amount_tiyin)
    if rest:
        commission_pct = float(rest.commission_percent or 0)
        if commission_pct > 0:
            commission_uzs = round(paid_uzs * commission_pct / 100.0, 2)
            cp = CommissionPayment(
                restaurant_id=rest.id,
                amount=commission_uzs,
                commission_percent=commission_pct,
                orders_revenue=paid_uzs,
                order_id=order.id,
                payment_charge_id=telegram_payment_charge_id,
                note=f"Telegram {provider} payment for order #{order.id}",
                status="confirmed",
            )
            db.add(cp)
            await db.commit()
            await db.refresh(cp)
            commission_id = cp.id

    # 4. Platforma adminga Telegram xabar (Faza 6: monitoring)
    try:
        from api.services.notifier import notify_platform_admin, order_payment_text
        if rest:
            await notify_platform_admin(
                order_payment_text(
                    order_id=order.id,
                    rest_name=rest.name,
                    amount_uzs=int(paid_uzs),
                    commission_uzs=commission_uzs,
                )
            )
    except Exception:
        pass

    # 5. POS dispatch — fiskal chek + restoran kassasiga (Faza 4.3)
    # Fire-and-forget: tashqi POS API yiqilsa ham asosiy to'lov oqimini bloklamaydi
    if order.status == OrderStatus.confirmed:
        try:
            import asyncio
            from api.services.pos_adapter import adapter as pos_adapter
            from api.database import AsyncSessionLocal

            async def _post_payment_dispatch(oid: int):
                """To'lov tasdiqlangach: POS + kuryer + restoran admin xabarlari."""
                async with AsyncSessionLocal() as bg_db:
                    fresh = (await bg_db.execute(
                        select(Order).options(selectinload(Order.items)).where(Order.id == oid)
                    )).scalar_one_or_none()
                    if not fresh:
                        return

                    # 5a. POS — fiskal chek va restoran kassasiga
                    try:
                        await pos_adapter.dispatch_order(bg_db, fresh)
                    except Exception as e:
                        log_critical(
                            "pos", "POS dispatch failed (post-payment)",
                            order_id=oid, error=str(e),
                        )

                    # 5b. Kuryer dispatch — provider tanlash (Yandex yoki o'z)
                    if fresh.delivery_type and fresh.delivery_type.value == "delivery":
                        yandex_done = False
                        try:
                            from api.services.delivery import dispatch_order_to_provider
                            dispatch_result = await dispatch_order_to_provider(fresh, bg_db)
                            if (
                                dispatch_result
                                and dispatch_result.get("provider") == "yandex"
                                and not dispatch_result.get("error")
                                and dispatch_result.get("claim_id")
                            ):
                                yandex_done = True
                                # Mijozga Yandex tracking URL bilan xabar
                                try:
                                    from sqlalchemy import select as _sel
                                    from database.models import User as _User
                                    user_q = await bg_db.execute(
                                        _sel(_User).where(_User.id == fresh.user_id)
                                    )
                                    user_obj = user_q.scalar_one_or_none()
                                    if user_obj and user_obj.telegram_id:
                                        rest_q2 = await bg_db.execute(
                                            select(Restaurant).where(Restaurant.id == fresh.restaurant_id)
                                        )
                                        rest_obj2 = rest_q2.scalar_one_or_none()
                                        bg_token = (rest_obj2.bot_token if rest_obj2 else "") or os.getenv("BOT_TOKEN", "")
                                        if bg_token:
                                            import httpx
                                            track_url = dispatch_result.get("tracking_url") or fresh.yandex_tracking_url
                                            track_text = (
                                                f"🚗 <b>Buyurtma #{fresh.id} — Yandex Delivery</b>\n\n"
                                                f"⏳ Kuryer izlanmoqda...\n"
                                            )
                                            if track_url:
                                                track_text += f"\n📍 <a href='{track_url}'>Buyurtmani kuzatish</a>"
                                            async with httpx.AsyncClient(timeout=5.0) as cli:
                                                await cli.post(
                                                    f"https://api.telegram.org/bot{bg_token}/sendMessage",
                                                    json={
                                                        "chat_id": user_obj.telegram_id,
                                                        "text": track_text,
                                                        "parse_mode": "HTML",
                                                        "disable_web_page_preview": True,
                                                    },
                                                )
                                except Exception as e:
                                    log_critical(
                                        "yandex", "Tracking URL notify failed",
                                        order_id=oid, error=str(e),
                                    )
                        except Exception as e:
                            log_critical(
                                "yandex", "Yandex dispatch failed (post-payment)",
                                order_id=oid, error=str(e),
                            )

                        # Yandex ulanmasa yoki xato bo'lsa — o'z kuryerlarga xabar
                        if not yandex_done:
                            try:
                                from api.routes.orders import _notify_couriers_new_order
                                await _notify_couriers_new_order(bg_db, fresh)
                            except Exception as e:
                                log_critical(
                                    "courier", "Notify couriers failed (post-payment)",
                                    order_id=oid, error=str(e),
                                )

                    # 5c. Restoran adminga Telegram xabar (yangi paid order)
                    try:
                        from api.services.notifier import notify_restaurant_admin
                        rest_q = await bg_db.execute(
                            select(Restaurant).where(Restaurant.id == fresh.restaurant_id)
                        )
                        rest_obj = rest_q.scalar_one_or_none()
                        if rest_obj and rest_obj.bot_token:
                            from html import escape as _esc
                            items_count = sum(i.quantity for i in (fresh.items or []))
                            text = (
                                f"💰 <b>Yangi to'langan buyurtma #{fresh.id}</b>\n\n"
                                f"📦 Mahsulotlar: {items_count} ta\n"
                                f"💵 Summa: <b>{int(fresh.total_price or 0):,} so'm</b>\n"
                                f"🚗 Turi: {fresh.delivery_type.value if fresh.delivery_type else '—'}\n"
                            )
                            if fresh.address:
                                text += f"📍 Manzil: {_esc(str(fresh.address))[:120]}\n"
                            if fresh.comment:
                                text += f"💬 Izoh: {_esc(str(fresh.comment))[:200]}\n"
                            text += f"\n⚡ Tayyorlashni boshlang!"
                            # admin_telegram_chat_id Restaurant'da bo'lsa shunga, aks holda asosiy bot orqali admin'ga
                            await notify_restaurant_admin(
                                restaurant_bot_token=rest_obj.bot_token,
                                admin_chat_id=getattr(rest_obj, "admin_telegram_chat_id", None),
                                text=text,
                            )
                    except Exception as e:
                        log_critical(
                            "notifier", "Restaurant admin notification failed",
                            order_id=oid, error=str(e),
                        )

            asyncio.create_task(_post_payment_dispatch(order.id))
        except Exception:
            pass

    return ConfirmResult(
        ok=True,
        order_id=order.id,
        paid_amount_tiyin=amount_tiyin,
        booking_id=booking_id,
        commission_id=commission_id,
        vat_amount_tiyin=order.vat_amount_tiyin or 0,
        fiscal_qr=order.fiscal_qr,
    )
