"""Restoran admini va platforma adminlariga Telegram orqali ogohlantirish.

Foydalanish hollari:
- Tarif 3 yoki 1 kun qoldi → restoran adminiga
- Grace boshlandi → restoran adminiga
- Suspended → restoran adminiga + platforma adminiga (ALERT_CHAT_ID)
- Queued tarif faollashdi → restoran adminiga
- INN tasdiqlanmadi → restoran adminiga

Tashqi `httpx.AsyncClient` orqali Telegram Bot API ishlatadi. Restoran
adminining Telegram chat ID'sini topish strategiyasi:
- Restaurant.admin_telegram_chat_id (yangi maydon — TODO)
- Yoki Telegram chat'ni linklash uchun deeplinking flow (kelajakda)
- Hozir: `ADMIN_CHAT_ID` env'dagi global chat (super-admin Telegram'i) ga
  ham, restoran admini Telegram orqali ulanmagani uchun, faqat platforma
  adminga yuboramiz va restoran admin uchun email/SMS keyinroq qo'shiladi.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from api.config import settings
from api.logging_config import log_critical


TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


async def _send_telegram(
    *, bot_token: str, chat_id: str, text: str, parse_mode: str = "HTML",
) -> bool:
    """Bitta Telegram xabarni jo'natish (silent fail)."""
    if not bot_token or not chat_id or not text:
        return False
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                TELEGRAM_API_BASE.format(token=bot_token),
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
            )
            if r.status_code != 200:
                log_critical(
                    "notifier", "Telegram send failed",
                    chat_id=chat_id, http_code=r.status_code,
                )
                return False
        return True
    except Exception as e:
        log_critical("notifier", "Telegram exception", error=str(e), chat_id=chat_id)
        return False


# ── Platforma admin (super-admin Telegram) ──────────────

async def notify_platform_admin(text: str) -> bool:
    """ALERT_CHAT_ID + ALERT_BOT_TOKEN orqali platforma adminga.

    Loyiha alerts.py ham shu tokenlarni ishlatadi — bir xil Telegram chat'ga
    fokuslantirilgan.
    """
    token = (settings.ALERT_BOT_TOKEN or "").strip()
    chat = (settings.ALERT_CHAT_ID or "").strip()
    if not token or not chat:
        # Konfiguratsiya yo'q — sokin chiqib ketamiz (logging_config alerts ham shunday)
        return False
    return await _send_telegram(bot_token=token, chat_id=chat, text=text)


# ── Restoran admin (uning bot orqali) ───────────────────

async def notify_restaurant_admin(
    *,
    restaurant_bot_token: Optional[str],
    admin_chat_id: Optional[str],
    text: str,
) -> bool:
    """Restoran adminiga uning customer-bot tokeni orqali xabar yuborish.

    Restoran admini odatda o'z botini Telegram'da chatda foydalanmaydi
    — shuning uchun `admin_chat_id` ko'pincha o'rnatilmagan. Bu funksiya
    konfiguratsiya bo'lganda ishlaydi, aks holda False qaytaradi.

    Kelajakda: bot ichida `/connect_admin` deeplink → admin_telegram_chat_id ni
    saqlash, shu sxema bilan to'liq ishlaydi.
    """
    if not restaurant_bot_token or not admin_chat_id:
        return False
    return await _send_telegram(
        bot_token=restaurant_bot_token, chat_id=admin_chat_id, text=text,
    )


# ── Yuqori darajadagi xabar shablonlari ─────────────────

def expiry_warning_text(rest, days_left: int) -> str:
    """3 yoki 1 kun qoldi xabari."""
    return (
        f"⚠️ <b>Tarifingiz tez orada tugaydi!</b>\n\n"
        f"🏪 Restoran: <b>{rest.name}</b>\n"
        f"📅 Qoldi: <b>{days_left} kun</b>\n"
        f"💳 Vaqtida to'lov qilmasangiz, 10 kunlik imtiyozli davr (grace period) boshlanadi.\n"
        f"Undan keyin xizmat to'xtatiladi.\n\n"
        f"Yangilash uchun admin panel → Tariflar bo'limi."
    )


def grace_started_text(rest) -> str:
    return (
        f"🟡 <b>Imtiyozli davr boshlandi</b>\n\n"
        f"🏪 Restoran: <b>{rest.name}</b>\n"
        f"⏳ Tarifingiz muddati o'tdi.\n"
        f"📅 Sizga 10 kun qo'shimcha vaqt berilyapti — shu davr ichida to'lov qiling,\n"
        f"aks holda hizmatlar to'xtatiladi."
    )


def suspended_text(rest) -> str:
    return (
        f"🔴 <b>Hizmatlar TO'XTATILDI</b>\n\n"
        f"🏪 Restoran: <b>{rest.name}</b>\n"
        f"❌ Imtiyozli davr (10 kun) tugadi va to'lov qilinmadi.\n"
        f"Bot va admin panel hozirgi vaqtda ishlamaydi.\n\n"
        f"Tiklanish: tarif uchun to'lov qilish kifoya."
    )


def queued_applied_text(rest, plan_name: str) -> str:
    return (
        f"✅ <b>Yangi tarif faollashdi</b>\n\n"
        f"🏪 Restoran: <b>{rest.name}</b>\n"
        f"📦 Tarif: <b>{plan_name}</b>\n"
        f"📅 30 kun davomida amal qiladi."
    )


def upgrade_success_text(rest_name: str, plan_name: str, amount_uzs: int, upgrade_type: str) -> str:
    """SaaS to'lov muvaffaqiyatli bo'lganda platforma adminga xabar."""
    type_label = {
        "immediate": "🚀 Hozir o'tish (kunlar muzlatildi)",
        "queued":    "📅 Navbat bilan o'tish",
        "renewal":   "🔄 Tarif yangilash",
        "initial":   "🆕 Birinchi tarif",
    }.get(upgrade_type, upgrade_type)
    return (
        f"💸 <b>SaaS to'lov muvaffaqiyatli</b>\n\n"
        f"🏪 Restoran: <b>{rest_name}</b>\n"
        f"📦 Tarif: <b>{plan_name}</b>\n"
        f"💰 Summa: <b>{amount_uzs:,} so'm</b>\n"
        f"📋 Turi: {type_label}"
    )


def order_payment_text(order_id: int, rest_name: str, amount_uzs: int, commission_uzs: float) -> str:
    """Customer order to'lovi muvaffaqiyatli bo'lganda platforma adminga."""
    return (
        f"🛒 <b>Yangi buyurtma to'landi</b>\n\n"
        f"🏪 Restoran: <b>{rest_name}</b>\n"
        f"📦 Order: <b>#{order_id}</b>\n"
        f"💰 Summa: <b>{amount_uzs:,} so'm</b>\n"
        f"💵 Platforma komissiyasi: <b>{commission_uzs:,.0f} so'm</b>"
    )


def webhook_security_text(category: str, error: str, details: dict) -> str:
    """Webhook xavfsizlik xatosi (signature/IP)."""
    parts = [
        f"⚠️ <b>Webhook xavfsizlik xatosi</b>",
        f"🔒 Tur: <code>{category}</code>",
        f"❌ Sabab: {error}",
    ]
    for k, v in (details or {}).items():
        parts.append(f"  • <code>{k}</code>: {str(v)[:80]}")
    return "\n".join(parts)


def daily_summary_text(summary: dict) -> str:
    """Platforma admin uchun har kuni 10:00 dagi qisqa hisobot."""
    parts = [
        "📊 <b>Subscription Daily Check</b>",
        f"🕙 Vaqt: {summary.get('started_at', '?')[:19]}",
    ]
    if summary.get("graced"):
        parts.append(f"🟡 Grace'ga o'tdi: <b>{len(summary['graced'])}</b> ta")
    if summary.get("suspended"):
        parts.append(f"🔴 Suspended: <b>{len(summary['suspended'])}</b> ta")
    if summary.get("queued_applied"):
        parts.append(f"✅ Queued upgrade qo'llandi: <b>{len(summary['queued_applied'])}</b> ta")
    if summary.get("frozen_expired"):
        parts.append(f"❄️ Muzlatilgan kunlar tugadi: <b>{len(summary['frozen_expired'])}</b>")
    if summary.get("warnings_3d") or summary.get("warnings_1d"):
        parts.append(
            f"⏰ Ogohlantirish yuborildi: 3-kun {len(summary.get('warnings_3d', []))}, "
            f"1-kun {len(summary.get('warnings_1d', []))}"
        )
    if len(parts) == 2:
        parts.append("✅ Bugun hech qanday status o'zgarishi yo'q.")
    return "\n".join(parts)
