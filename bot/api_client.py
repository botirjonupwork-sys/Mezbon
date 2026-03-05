import httpx
import os

BASE_URL = os.getenv("API_URL", "http://localhost:8000")


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
        r = await client.get(f"{BASE_URL}/menu/categories")
        return r.json()


async def get_products(category_id: int):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/menu/categories/{category_id}/products")
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
            params={"telegram_id": telegram_id},
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
    """settings.json dan restoran sozlamalarini olish."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{BASE_URL}/admin/settings", timeout=3.0)
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
