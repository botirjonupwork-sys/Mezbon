"""Telegram Native Payments handlerlari (aiogram 3).

3 ta event handle qilamiz:

1. **Mijoz "💳 To'lov" bosadi** → `send_invoice_for_order()`
   FastAPI'dan invoice payload olamiz va Telegram'ga uzatamiz

2. **`pre_checkout_query`** → bot Telegram'ga ok=True/False qaytarishi shart
   FastAPI `/precheck` endpoint orqali oxirgi marta resurs (mashina) tekshiriladi

3. **`successful_payment`** → to'lov muvaffaqiyatli o'tdi
   FastAPI `/confirm` chaqiriladi → order paid + mashina band + komissiya yoziladi

Tip: aiogram 3.7+ bilan `Message.successful_payment` field paydo bo'ladi.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery, LabeledPrice, Message, PreCheckoutQuery,
)

from bot import api_client


router = Router(name="payments")
log = logging.getLogger(__name__)


# ── Step 1: invoice yuborish ─────────────────────────────────────────────

async def send_invoice_for_order(
    message: Message,
    order_id: int,
    provider: str = "click",
) -> None:
    """Buyurtma uchun Telegram invoice yuboradi.

    Boshqa handler (masalan, "Confirm order" tugmasidan keyin) chaqiradi.
    """
    try:
        payload = await api_client.tg_payment_prepare(order_id, provider)
    except Exception as e:
        log.exception("invoice prepare failed")
        # 503 — provider token sozlanmagan
        msg = str(e)
        if "503" in msg or "provider_token_missing" in msg:
            await message.answer(
                "⚠️ <b>Karta orqali to'lov hozircha sozlanmagan</b>\n\n"
                f"Restoran administratori Click/Payme sozlamalarini hali "
                f"to'liq amalga oshirmagan. Iltimos:\n\n"
                f"💵 <b>Naqd to'lovni</b> tanlang yoki\n"
                f"📞 Restoran bilan bog'laning.\n\n"
                f"<i>Texnik: provider_token sozlanmagan ({provider})</i>",
                parse_mode="HTML",
            )
        else:
            await message.answer(f"❌ To'lov tayyorlashda xato: {e}")
        return

    prices = [
        LabeledPrice(label=p["label"], amount=int(p["amount"]))
        for p in payload.get("prices", [])
    ]
    if not prices:
        await message.answer("❌ Buyurtma summasi 0 — to'lov yaratib bo'lmaydi")
        return

    try:
        await message.bot.send_invoice(
            chat_id=message.chat.id,
            title=payload["title"],
            description=payload["description"],
            payload=payload["payload"],          # 'order_<id>'
            provider_token=payload["provider_token"],
            currency=payload["currency"],         # 'UZS'
            prices=prices,
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False,
            # Mahalliy chek format va sarlavhasi qo'shimcha provider_data orqali
            # Click/Payme uchun tunable; default qoldiramiz.
        )
    except TelegramBadRequest as e:
        log.exception("send_invoice failed")
        await message.answer(
            f"❌ Telegram to'lov yaratilmadi: {e.message}\n"
            f"Restoran administratoriga murojaat qiling."
        )


# ── Step 2: pre_checkout_query — oxirgi resurs tekshiruvi ──────────────

@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    """Telegram bizdan to'lov o'tkazilishini tasdiqlashni so'raydi.

    10 sekund ichida `query.answer(ok=True/False)` chaqirish kerak.
    Aks holda Telegram to'lovni rad etadi va mijoz "Payment failed" ko'radi.
    """
    payload = query.invoice_payload or ""
    if not payload.startswith("order_"):
        await query.answer(ok=False, error_message="Noto'g'ri to'lov ma'lumoti")
        return

    try:
        order_id = int(payload.split("_", 1)[1])
    except (ValueError, IndexError):
        await query.answer(ok=False, error_message="Order ID o'qib bo'lmadi")
        return

    try:
        result = await api_client.tg_payment_precheck(order_id)
    except Exception as e:
        log.exception("precheck failed")
        await query.answer(
            ok=False,
            error_message="Tizim hozir mavjud emas. Keyinroq urinib ko'ring.",
        )
        return

    if not result.get("ok"):
        reason_code = result.get("reason_code") or "unknown"
        msg = result.get("error_message") or "To'lov hozir o'tkazib bo'lmaydi"
        # Foydalanuvchi do'stona xabar — Telegram error_message max 255 belgi
        friendly_map = {
            "no_car": "Mashinalarimiz to'liq band. Boshqa vaqtga qayta urinib ko'ring.",
            "no_branch": "Filial topilmadi. Restoranga qo'ng'iroq qiling.",
            "already_paid": "Bu buyurtma allaqachon to'langan.",
            "cancelled": "Buyurtma bekor qilingan.",
            "order_not_found": "Buyurtma topilmadi.",
        }
        friendly = friendly_map.get(reason_code, msg)
        await query.answer(ok=False, error_message=friendly[:255])
        log.info("pre_checkout rejected: order=%s reason=%s", order_id, reason_code)
        return

    await query.answer(ok=True)


# ── Step 3: successful_payment — to'lov muvaffaqiyatli o'tdi ──────────

@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    """Mijoz haqiqatan ham pulni to'ladi.

    Bu paytgacha pre_checkout o'tib bo'lgan, ya'ni mashina ham bo'sh edi.
    Endi:
        - Order.status = confirmed
        - DeliveryCarBooking yaratiladi (mashina band)
        - CommissionPayment yoziladi
    """
    sp = message.successful_payment
    if not sp:
        return

    payload = sp.invoice_payload or ""
    if not payload.startswith("order_"):
        await message.answer("⚠️ To'lov payload'i tanilmadi — administratorga murojaat qiling.")
        return

    try:
        order_id = int(payload.split("_", 1)[1])
    except (ValueError, IndexError):
        await message.answer("⚠️ Order ID o'qib bo'lmadi")
        return

    # is_prepayment va provider invoice'da metada saqlanadi —
    # biz buni payload orqali emas, FastAPI hal qiladi (Order.is_prepayment yangilanadi)
    provider_used = "click"   # default; haqiqiy provider Telegram emas, sb'ningiki

    try:
        result = await api_client.tg_payment_confirm(
            order_id=order_id,
            amount_tiyin=int(sp.total_amount),
            provider=provider_used,
            telegram_payment_charge_id=sp.telegram_payment_charge_id,
            provider_payment_charge_id=sp.provider_payment_charge_id,
        )
    except Exception as e:
        log.exception("confirm failed")
        await message.answer(
            "✅ To'lov qabul qilindi, lekin ichki tizimda muammo yuz berdi.\n"
            f"Iltimos, administratorga buyurtma raqamini ayting: #{order_id}\n"
            f"Telegram tx: {sp.telegram_payment_charge_id}",
        )
        return

    # Foydalanuvchiga chiroyli xabar — bitta yagona tasdiqlash
    amount_uzs = sp.total_amount / 100
    booking_id = result.get("booking_id")
    text_lines = [
        "✅ <b>Buyurtma tasdiqlandi va to'lov qabul qilindi!</b>",
        "",
        f"📦 Buyurtma: <b>#{order_id}</b>",
        f"💰 To'langan summa: <b>{int(amount_uzs):,} so'm</b>",
        f"💳 Karta: {provider_used.title()} (Telegram)",
    ]
    # Faza 6: VAT/QQS ma'lumoti
    vat_tiyin = result.get("vat_amount_tiyin") or 0
    if vat_tiyin > 0:
        text_lines.append(f"📊 QQS (12%): <b>{int(vat_tiyin/100):,} so'm</b>")
    if booking_id:
        text_lines.append(f"🚗 Mashina band qilindi (booking #{booking_id})")
    # Faza 6: fiskal QR (NeonAlisa)
    fiscal_qr = result.get("fiscal_qr")
    if fiscal_qr:
        text_lines.append(f"🧾 Fiskal chek: <a href='{fiscal_qr}'>QR kod</a>")
    text_lines.append("")
    text_lines.append("📞 Tez orada operator siz bilan bog'lanadi.")
    text_lines.append("Hamkorligingiz uchun rahmat! 🙏")

    from bot.keyboards.main import main_menu_kb
    await message.answer("\n".join(text_lines), parse_mode="HTML")
    await message.answer("Asosiy menyuga qaytdik.", reply_markup=main_menu_kb())


# ── Inline tugma orqali to'lov boshlash ────────────────────────────────

@router.callback_query(F.data.startswith("tgpay:"))
async def on_pay_callback(callback: CallbackQuery) -> None:
    """`tgpay:<order_id>:<provider>` callback — Telegram invoice yuboradi."""
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Noto'g'ri to'lov ma'lumoti", show_alert=True)
        return
    try:
        order_id = int(parts[1])
    except ValueError:
        await callback.answer("Order ID xato", show_alert=True)
        return
    provider = parts[2]
    if provider not in ("click", "payme"):
        await callback.answer("Provider faqat click yoki payme", show_alert=True)
        return

    await callback.answer(f"To'lov yaratilmoqda ({provider})...")
    # Tugmalarni saqlab qolamiz — to'lov muvaffaqiyatsiz bo'lsa, foydalanuvchi
    # qayta urinishi mumkin (boshqa karta bilan, masalan).
    # Muvaffaqiyatli to'lovdan keyin on_successful_payment yangi xabar yuboradi
    # va eski tugmalarni keraksiz qiladi (ular hech narsa qilmaydi, chunki
    # order allaqachon paid).
    await send_invoice_for_order(callback.message, order_id, provider)


# ── To'lashdan oldin buyurtmani bekor qilish ───────────────────────────

@router.callback_query(F.data.startswith("tgpay_cancel:"))
async def on_pay_cancel(callback: CallbackQuery) -> None:
    """`tgpay_cancel:<order_id>` — to'lov yarataylish bosqichida buyurtmani bekor qiladi."""
    parts = (callback.data or "").split(":")
    if len(parts) != 2:
        await callback.answer("Noto'g'ri ma'lumot", show_alert=True)
        return
    try:
        order_id = int(parts[1])
    except ValueError:
        await callback.answer("Order ID xato", show_alert=True)
        return

    try:
        await api_client.cancel_unpaid_order(order_id)
    except Exception as e:
        log.exception("cancel unpaid failed")
        await callback.answer(f"Bekor qilishda xato: {e}", show_alert=True)
        return

    from bot.keyboards.main import main_menu_kb
    try:
        await callback.message.edit_text(
            f"❌ <b>Buyurtma #{order_id} bekor qilindi</b>\n\n"
            f"To'lov amalga oshirilmadi. Yangi buyurtma berishingiz mumkin.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.message.answer("Asosiy menyuga qaytdik.", reply_markup=main_menu_kb())
    await callback.answer("Buyurtma bekor qilindi")


# ── Test command ────────────────────────────────────────────────────────

@router.message(Command("pay"))
async def cmd_pay(message: Message) -> None:
    """Test uchun: `/pay <order_id> [click|payme]`"""
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Foydalanish: /pay <order_id> [click|payme]")
        return
    try:
        order_id = int(parts[1])
    except ValueError:
        await message.answer("order_id raqam bo'lishi kerak")
        return
    provider = parts[2] if len(parts) > 2 else "click"
    await send_invoice_for_order(message, order_id, provider)
