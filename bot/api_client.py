import httpx
import os

BASE_URL = os.getenv("API_URL", "http://localhost:8000")
BOT_SECRET = os.getenv("SECRET_KEY", "")  # API bilan bir xil SECRET_KEY
_BOT_HEADERS = {"X-Bot-Secret": BOT_SECRET} if BOT_SECRET else {}

# ── Multi-restaurant auth state ──────────────────────
_auth_token: str = ""
_restaurant_id: int = 1


def set_auth(token: str, restaurant_id: int):
    """Bot uchun auth token va restaurant_id saqlash."""
    global _auth_token, _restaurant_id
    _auth_token = token
    _restaurant_id = restaurant_id


def get_restaurant_id() -> int:
    return _restaurant_id


async def bot_login(bot_token: str) -> dict:
    """Bot tokenni API ga yuborib, restaurant_id olish."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/auth/bot-login",
            json={"bot_token": bot_token},
            timeout=5.0,
        )
        r.raise_for_status()
        return r.json()


async def get_user(telegram_id: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/users/{telegram_id}")
        if r.status_code == 200:
            return r.json()
        return None


async def create_user(telegram_id: str, full_name: str, phone: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/users/", json={
            "telegram_id": telegram_id,
            "full_name": full_name,
            "phone": phone,
        })
        return r.json()


async def set_user_branch(telegram_id: str, branch_id):
    """branch_id: int yoki None"""
    """Foydalanuvchining tanlangan filialini DB'ga saqlash. User bo'lmasa False qaytaradi."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{BASE_URL}/users/{telegram_id}/branch",
                json={"branch_id": branch_id},
            )
            return r.status_code == 200
    except Exception:
        return False


async def get_categories():
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/menu/categories",
            params={"restaurant_id": _restaurant_id},
        )
        return r.json()


async def get_products(category_id: int):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/menu/categories/{category_id}/products",
            params={"restaurant_id": _restaurant_id},
        )
        return r.json()


async def get_product(product_id: int):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/menu/products/{product_id}")
        if r.status_code == 200:
            return r.json()
        return None


async def create_order(telegram_id: str, order_data: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/orders/",
            params={"telegram_id": telegram_id, "restaurant_id": _restaurant_id},
            json=order_data,
        )
        if r.status_code in (200, 201):
            return r.json()
        return None


async def get_user_orders(telegram_id: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/orders/user/{telegram_id}",
            params={"restaurant_id": _restaurant_id},  # SaaS izolatsiya
        )
        if r.status_code == 200:
            return r.json()
        return []


async def get_addresses(telegram_id: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/users/{telegram_id}/addresses")
        if r.status_code == 200:
            return r.json()
        return []


async def add_address(telegram_id: str, title: str, address: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/users/{telegram_id}/addresses",
            json={"title": title, "address": address},
        )
        return r.json()


async def get_catering_booked(branch_id: int = None) -> dict:
    """Catering uchun band qilingan kun va vaqtlar.

    Returns: {"YYYY-MM-DD": ["HH:MM", ...], ...}
    """
    params = {"restaurant_id": _restaurant_id}
    if branch_id:
        params["branch_id"] = branch_id
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(f"{BASE_URL}/catering/booked-dates", params=params)
            if r.status_code == 200:
                return (r.json() or {}).get("booked", {})
    except Exception:
        pass
    return {}


async def get_settings() -> dict:
    """Restoran haqida ommaviy ma'lumot (auth shart emas)."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{BASE_URL}/restaurants/{_restaurant_id}/info",
                timeout=3.0,
            )
            if r.status_code == 200:
                d = r.json()
                # Bot eski "restaurant_name" kalitidan foydalanadi
                d["restaurant_name"] = d.get("name", "")
                return d
        except Exception:
            pass
    return {}


async def create_review(telegram_id: str, rating: int, comment: str = ""):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/reviews/",
            params={
                "telegram_id": telegram_id,
                "restaurant_id": _restaurant_id,  # SaaS izolatsiya
            },
            json={"rating": rating, "comment": comment},
        )
        return r.json()


async def get_restaurant_branches(restaurant_id: int = None):
    """Restaurantning barcha faol filiallarini olish."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{BASE_URL}/admin/branches",
                params={"restaurant_id": restaurant_id or _restaurant_id},
                timeout=5.0,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return []


async def get_nearest_branches(lat: float, lon: float, restaurant_id: int = None):
    """Yaqin filiallarni masofasi bilan qaytaradi."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{BASE_URL}/branches/nearest",
                params={"lat": lat, "lon": lon, "restaurant_id": restaurant_id or _restaurant_id},
                timeout=5.0,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return []


async def get_branch(branch_id: int):
    """Filial ma'lumotlarini olish."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{BASE_URL}/branches/{branch_id}", timeout=5.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return None


async def get_branch_categories(branch_id: int):
    """Filial bo'yicha kategoriyalarni olish."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/menu/categories",
            params={"branch_id": branch_id},
        )
        return r.json()


async def get_branch_products(category_id: int, branch_id: int):
    """Filial bo'yicha mahsulotlarni olish."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/menu/categories/{category_id}/products",
            params={"branch_id": branch_id},
        )
        return r.json()


# ── Catering (tadbir) API ───────────────────────────

async def get_catering_groups():
    """Barcha catering guruhlari (somsa va non)."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/catering/groups",
            params={"restaurant_id": _restaurant_id},
        )
        if r.status_code == 200:
            return r.json()
        return []


async def calculate_catering_price_multi(group: str, items: list, delivery_subtype: str, distance_km: float = None):
    """Aralash catering buyurtma narxini hisoblash.

    items = [{product_id: int, quantity: int}, ...]
    """
    payload = {
        "group": group,
        "items": items,
        "delivery_subtype": delivery_subtype,
    }
    if distance_km is not None:
        payload["distance_km"] = distance_km
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/catering/calculate-price",
            params={"restaurant_id": _restaurant_id},
            json=payload,
        )
        if r.status_code == 200:
            return r.json()
        return {"error": r.text}


async def create_catering_order(telegram_id: str, order_data: dict, branch_id: int = None):
    """Catering buyurtma yaratish (X-Bot-Secret header bilan)."""
    params = {"telegram_id": telegram_id, "restaurant_id": _restaurant_id}
    if branch_id:
        params["branch_id"] = branch_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{BASE_URL}/catering/orders",
            params=params,
            json=order_data,
            headers=_BOT_HEADERS,
        )
        if r.status_code in (200, 201):
            return r.json()
        # Detail xabarini chiqarib qaytarish (409 va boshq.)
        try:
            body = r.json()
            detail = body.get("detail") if isinstance(body, dict) else None
        except Exception:
            detail = None
        return {"error": detail or r.text, "status_code": r.status_code}


# ── Telegram Native Payments (faza 4) ─────────────────────────────────

async def tg_payment_prepare(order_id: int, provider: str = "click") -> dict:
    """`/payments/telegram/prepare` — invoice payload tayyorlash.

    Qaytadi: prices, provider_token, total_tiyin, is_prepayment, ...
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{BASE_URL}/payments/telegram/prepare",
            json={"order_id": order_id, "provider": provider},
            headers=_BOT_HEADERS,
        )
        r.raise_for_status()
        return r.json()


async def tg_payment_summary(order_id: int) -> dict:
    """`/payments/telegram/summary` — UI uchun ko'rsatma (chek bo'lmagan)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{BASE_URL}/payments/telegram/summary",
            json={"order_id": order_id},
            headers=_BOT_HEADERS,
        )
        r.raise_for_status()
        return r.json()


async def tg_payment_precheck(order_id: int) -> dict:
    """`/payments/telegram/precheck` — pre_checkout_query'da chaqiriladi.

    Qaytadi: {ok: bool, error_message, reason_code}
    """
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.post(
            f"{BASE_URL}/payments/telegram/precheck",
            json={"order_id": order_id},
            headers=_BOT_HEADERS,
        )
        r.raise_for_status()
        return r.json()


async def tg_payment_confirm(
    *,
    order_id: int,
    amount_tiyin: int,
    provider: str,
    telegram_payment_charge_id: str = None,
    provider_payment_charge_id: str = None,
    is_prepayment: bool = False,
    prepayment_percent: int = None,
) -> dict:
    """`/payments/telegram/confirm` — successful_payment'da chaqiriladi."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{BASE_URL}/payments/telegram/confirm",
            json={
                "order_id": order_id,
                "amount_tiyin": amount_tiyin,
                "provider": provider,
                "telegram_payment_charge_id": telegram_payment_charge_id,
                "provider_payment_charge_id": provider_payment_charge_id,
                "is_prepayment": is_prepayment,
                "prepayment_percent": prepayment_percent,
            },
            headers=_BOT_HEADERS,
        )
        r.raise_for_status()
        return r.json()


async def cancel_unpaid_order(order_id: int) -> dict:
    """`/payments/telegram/cancel-unpaid` — to'lanmagan buyurtmani bekor qilish."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.post(
            f"{BASE_URL}/payments/telegram/cancel-unpaid",
            json={"order_id": order_id},
            headers=_BOT_HEADERS,
        )
        r.raise_for_status()
        return r.json()
