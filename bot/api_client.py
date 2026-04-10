import httpx
import os

BASE_URL = os.getenv("API_URL", "http://localhost:8000")

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
        r = await client.get(f"{BASE_URL}/orders/user/{telegram_id}")
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


async def get_settings() -> dict:
    """Restoran sozlamalarini olish (restaurant_id bilan)."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{BASE_URL}/admin/settings",
                params={"restaurant_id": _restaurant_id},
                timeout=3.0,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return {}


async def create_review(telegram_id: str, rating: int, comment: str = ""):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/reviews/",
            params={"telegram_id": telegram_id},
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
