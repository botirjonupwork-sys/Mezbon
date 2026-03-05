"""Yandex Delivery API integratsiyasi (Express / Same-day)"""
import os
import uuid
import json
import httpx

BASE_URL = "https://b2b.taxi.yandex.net/b2b/cargo/integration/v2"


def _load_restaurant() -> dict:
    """settings.json dan restoran koordinatalari va ma'lumotlarini olish."""
    try:
        with open(os.path.join(os.getcwd(), "settings.json"), "r") as f:
            return json.load(f)
    except Exception:
        return {}


async def create_delivery(
    customer_name: str,
    customer_phone: str,
    customer_address: str,
    customer_lat: float,
    customer_lon: float,
    order_id: int,
    items_description: str,
    total_price: float,
    comment: str = "",
) -> dict:
    """
    Yandex Delivery da yetkazib berish zakazini yaratish va tasdiqlash.

    Qaytaradi: {"claim_id": "...", "status": "..."} yoki None
    """
    token = os.getenv("YANDEX_DELIVERY_TOKEN", "")
    if not token:
        return None

    settings = _load_restaurant()
    rest_name = settings.get("restaurant_name", "Muhsina Dollar Somsa")
    rest_phone = settings.get("phone", "+998901234567")
    rest_address = settings.get("address", "Toshkent sh.")
    rest_lat = settings.get("restaurant_lat", 41.2995)
    rest_lon = settings.get("restaurant_lon", 69.2401)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept-Language": "ru",
    }

    request_id = str(uuid.uuid4())

    payload = {
        "items": [
            {
                "title": f"Zakaz #{order_id}",
                "size": {"length": 0.3, "width": 0.3, "height": 0.2},
                "weight": 2.0,
                "cost_value": str(total_price),
                "cost_currency": "UZS",
                "quantity": 1,
                "pickup_point": 1,
                "droff_point": 2,
            }
        ],
        "route_points": [
            {
                "point_id": 1,
                "visit_order": 1,
                "type": "source",
                "contact": {
                    "name": rest_name,
                    "phone": rest_phone,
                },
                "address": {
                    "fullname": rest_address,
                    "coordinates": [rest_lon, rest_lat],
                },
            },
            {
                "point_id": 2,
                "visit_order": 2,
                "type": "destination",
                "contact": {
                    "name": customer_name,
                    "phone": customer_phone,
                },
                "address": {
                    "fullname": customer_address,
                    "coordinates": [customer_lon, customer_lat],
                },
                "external_order_id": str(order_id),
            },
        ],
        "comment": comment or f"Zakaz #{order_id}: {items_description}",
        "client_requirements": {
            "taxi_class": "express",
        },
        "auto_accept": True,
        "callback_url": os.getenv("YANDEX_CALLBACK_URL", ""),
    }

    # callback_url bo'sh bo'lsa olib tashlaymiz
    if not payload["callback_url"]:
        del payload["callback_url"]

    try:
        async with httpx.AsyncClient() as client:
            # 1. Claim yaratish
            r = await client.post(
                f"{BASE_URL}/claims/create",
                params={"request_id": request_id},
                headers=headers,
                json=payload,
                timeout=15.0,
            )

            if r.status_code in (200, 201):
                claim = r.json()
                return {
                    "claim_id": claim.get("id"),
                    "status": claim.get("status"),
                    "version": claim.get("version", 1),
                }
            else:
                # Xato tafsilotlarini log qilamiz
                print(f"[Yandex] Claim create error {r.status_code}: {r.text}")
                return None

    except Exception as e:
        print(f"[Yandex] Exception: {e}")
        return None


async def get_claim_status(claim_id: str) -> dict:
    """Claim holatini tekshirish."""
    token = os.getenv("YANDEX_DELIVERY_TOKEN", "")
    if not token:
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/claims/info",
                params={"claim_id": claim_id},
                headers=headers,
                timeout=10.0,
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "claim_id": data.get("id"),
                    "status": data.get("status"),
                    "performer": data.get("performer_info"),
                    "pricing": data.get("pricing"),
                }
    except Exception:
        pass
    return None


async def cancel_claim(claim_id: str, version: int = 1) -> bool:
    """Claim ni bekor qilish."""
    token = os.getenv("YANDEX_DELIVERY_TOKEN", "")
    if not token:
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/claims/cancel",
                params={"claim_id": claim_id},
                headers=headers,
                json={
                    "cancel_state": "free",
                    "version": version,
                },
                timeout=10.0,
            )
            return r.status_code == 200
    except Exception:
        return False


async def check_price(
    customer_address: str,
    customer_lat: float,
    customer_lon: float,
) -> float:
    """Dastavka narxini hisoblash (claim yaratmasdan)."""
    token = os.getenv("YANDEX_DELIVERY_TOKEN", "")
    if not token:
        return None

    settings = _load_restaurant()
    rest_address = settings.get("address", "Toshkent sh.")
    rest_lat = settings.get("restaurant_lat", 41.2995)
    rest_lon = settings.get("restaurant_lon", 69.2401)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept-Language": "ru",
    }

    payload = {
        "items": [
            {
                "size": {"length": 0.3, "width": 0.3, "height": 0.2},
                "weight": 2.0,
                "quantity": 1,
            }
        ],
        "route_points": [
            {
                "coordinates": [rest_lon, rest_lat],
                "fullname": rest_address,
            },
            {
                "coordinates": [customer_lon, customer_lat],
                "fullname": customer_address,
            },
        ],
        "requirements": {
            "taxi_class": "express",
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/check-price",
                headers=headers,
                json=payload,
                timeout=10.0,
            )
            if r.status_code == 200:
                data = r.json()
                price = data.get("price")
                if price:
                    return float(price)
    except Exception:
        pass
    return None
