"""Mijoz buyurtma to'lovi — Click / Payme / Uzum direct app link generatori.

Bu modul foydalanuvchi qurilmasidagi haqiqiy to'lov app'iga yo'naltirish uchun
URL yaratadi. URL telefonda ochilganda:
  - app o'rnatilgan bo'lsa universal/app link orqali avtomatik ochiladi
  - app yo'q bo'lsa brauzerda web checkout ko'rsatiladi

Subscription (tarif) to'lovlaridan farqli o'laroq, bu yerda:
  * merchant_trans_id prefiksi `o-<order_id>-<rand>` (subscription'da `r-...`)
  * Webhook to'g'ridan-to'g'ri Order'ni yangilaydi (Payment yozuvi emas)
"""
from __future__ import annotations

import base64
import uuid
import urllib.parse
from decimal import Decimal
from typing import Optional

from database.models import Restaurant, Order


# ── Idempotency kalit ──────────────────────────────────────────────

def make_order_trans_id(order_id: int) -> str:
    """Buyurtma uchun unique merchant_trans_id."""
    rand = uuid.uuid4().hex[:8]
    return f"o-{order_id}-{rand}"


def is_order_trans_id(merchant_trans_id: str) -> bool:
    """Webhook'da prefiks bo'yicha order yoki subscription'ni ajratish."""
    return (merchant_trans_id or "").startswith("o-")


def parse_order_id(merchant_trans_id: str) -> Optional[int]:
    """`o-42-abc123` → 42"""
    if not is_order_trans_id(merchant_trans_id):
        return None
    parts = merchant_trans_id.split("-")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


# ── Yakuniy to'lov summasi (yagona manba) ──────────────────────────

def order_amount_uzs(order: Order) -> float:
    """Mijoz to'laydigan yakuniy summa (so'm) = mahsulotlar + dastavka."""
    return float(order.total_price or 0) + float(order.delivery_fee or 0)


def order_amount_tiyin(order: Order) -> int:
    """Yakuniy summa tiyin'da. To'lov URL va webhook tekshiruvi AYNAN shu
    funksiyani ishlatishi shart — aks holda summa mos kelmaydi (Payme -31001)."""
    return int(round(order_amount_uzs(order) * 100))


# ── Click ───────────────────────────────────────────────────────────

def build_click_url(
    *,
    merchant_id: str,
    service_id: str,
    amount_uzs: float,
    merchant_trans_id: str,
    return_url: Optional[str] = None,
) -> str:
    """Click hosted checkout URL — telefonda Click app o'rnatilgan bo'lsa avtomatik ochiladi.

    Click amount'ni decimal so'm sifatida kutadi (tiyin emas).
    """
    params = {
        "service_id": service_id,
        "merchant_id": merchant_id,
        "amount": f"{Decimal(str(amount_uzs)):.2f}",
        "transaction_param": merchant_trans_id,
    }
    if return_url:
        params["return_url"] = return_url
    query = urllib.parse.urlencode(params)
    return f"https://my.click.uz/services/pay?{query}"


# ── Payme ───────────────────────────────────────────────────────────

def build_payme_url(
    *,
    merchant_id: str,
    amount_tiyin: int,
    account: Optional[dict] = None,
    order_id: Optional[int] = None,
    return_url: Optional[str] = None,
    lang: str = "uz",
) -> str:
    """Payme checkout URL — rasmiy base64 format (yagona quruvchi).

    Rasmiy hujjat (developer.help.paycom.uz/initsializatsiya-platezhey):
      https://checkout.paycom.uz/<base64(m=X;ac.<field>=Y;a=Z;c=URL;ct=15000;l=uz)>
    Ajratuvchi — `;`. Summa — tiyin'da (1 UZS = 100 tiyin).

    `account` — Payme kassasiga sozlangan account maydonlari, masalan:
        {"order_id": 42}             → mijoz buyurtmasi
        {"merchant_trans_id": "r-…"} → obuna (subscription) to'lovi
    `order_id` — orqaga moslik uchun qisqa yo'l (account={"order_id": ...}).
    """
    if account is None:
        if order_id is None:
            raise ValueError("account yoki order_id berilishi shart")
        account = {"order_id": order_id}

    parts = [f"m={merchant_id}"]
    for field, value in account.items():
        parts.append(f"ac.{field}={value}")
    parts.append(f"a={amount_tiyin}")
    if return_url:
        parts.append(f"c={return_url}")
        parts.append("ct=15000")
    parts.append(f"l={lang}")
    blob = ";".join(parts).encode()
    # base64, padding olib tashlanadi (Payme checkout shu ko'rinishni kutadi)
    encoded = base64.b64encode(blob).decode().rstrip("=")
    return f"https://checkout.paycom.uz/{encoded}"


# ── Uzum ────────────────────────────────────────────────────────────

def build_uzum_url(
    *,
    service_id: str,
    amount_tiyin: int,
    order_id: int,
) -> str:
    """Uzum Bank Merchant — open-service URL.

    Format: https://www.uzumbank.uz/open-service?serviceId=X&amount=Y&order_id=Z
    Telefonda Uzum app o'rnatilgan bo'lsa universal link orqali avtomatik ochiladi.

    Amount tiyin'da.
    """
    params = {
        "serviceId": service_id,
        "amount": str(amount_tiyin),
        "order_id": str(order_id),
    }
    query = urllib.parse.urlencode(params)
    return f"https://www.uzumbank.uz/open-service?{query}"


# ── Provayder konfiguratsiyasi ─────────────────────────────────────

def get_enabled_providers(rest: Restaurant) -> list[str]:
    """Restoranda yoqilgan va sozlangan to'lov provayderlari."""
    providers = []
    if rest.click_enabled and rest.click_merchant_id and rest.click_service_id:
        providers.append("click")
    if rest.payme_enabled and rest.payme_merchant_id:
        providers.append("payme")
    if rest.uzum_enabled and rest.uzum_service_id:
        providers.append("uzum")
    return providers


def generate_payment_url(
    rest: Restaurant,
    order: Order,
    provider: str,
    return_url: Optional[str] = None,
) -> tuple[str, str]:
    """Buyurtma uchun to'lov URL'i va merchant_trans_id qaytaradi.

    Agar order.merchant_trans_id allaqachon o'rnatilgan bo'lsa, uni ishlatamiz
    (3 ta provayder URL'i bir xil ID ga ishora qiladi).
    return_url: bot'ga qaytarish uchun (https://t.me/<bot>?start=...).
    """
    merchant_trans_id = order.merchant_trans_id or make_order_trans_id(order.id)
    # Mijoz to'laydigan summa = mahsulotlar + dastavka (yagona manba)
    amount_uzs = order_amount_uzs(order)
    amount_tiyin = order_amount_tiyin(order)

    if provider == "click":
        url = build_click_url(
            merchant_id=rest.click_merchant_id,
            service_id=rest.click_service_id,
            amount_uzs=amount_uzs,
            merchant_trans_id=merchant_trans_id,
            return_url=return_url,
        )
    elif provider == "payme":
        url = build_payme_url(
            merchant_id=rest.payme_merchant_id,
            order_id=order.id,
            amount_tiyin=amount_tiyin,
            return_url=return_url,
        )
    elif provider == "uzum":
        url = build_uzum_url(
            service_id=rest.uzum_service_id,
            amount_tiyin=amount_tiyin,
            order_id=order.id,
        )
    else:
        raise ValueError(f"Noma'lum provider: {provider}")

    return url, merchant_trans_id
