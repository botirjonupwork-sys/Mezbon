"""Yandex Delivery B2B API client — claim yaratish, status kuzatish, bekor qilish.

API docs: https://yandex.com/support/delivery-profile/en/api/express/
Base URL: https://b2b.taxi.yandex.net/b2b/cargo/integration/v2/
Test URL: https://b2b.taxi.tst.yandex.net/b2b/cargo/integration/v2/
"""
import httpx
import uuid
from typing import Optional


PROD_URL = "https://b2b.taxi.yandex.net/b2b/cargo/integration/v2"
TEST_URL = "https://b2b.taxi.tst.yandex.net/b2b/cargo/integration/v2"


class YandexDeliveryError(Exception):
    pass


class YandexDeliveryClient:
    def __init__(self, api_token: str, test_mode: bool = True):
        self.api_token = api_token
        self.base_url = TEST_URL if test_mode else PROD_URL
        self.mock_mode = not api_token or api_token in ("test", "mock")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept-Language": "ru",
            "Content-Type": "application/json",
        }

    async def create_claim(
        self,
        *,
        pickup_address: str,
        pickup_lat: float,
        pickup_lon: float,
        pickup_phone: str,
        pickup_name: str,
        dropoff_address: str,
        dropoff_lat: float,
        dropoff_lon: float,
        dropoff_phone: str,
        dropoff_name: str,
        items: list[dict],
        total_price: float,
        comment: Optional[str] = None,
    ) -> dict:
        """Buyurtma yaratish — Yandex Delivery ga dastavka so'rovi yuborish.

        items: [{title, quantity, cost_value, weight_kg}, ...]

        Qaytaradi: {id, status, tracking_url, price}
        """
        if self.mock_mode:
            return self._mock_create_claim(items, total_price)

        payload = {
            "items": [
                {
                    "title": item["title"],
                    "quantity": item["quantity"],
                    "cost_value": str(item.get("cost_value", 0)),
                    "cost_currency": "UZS",
                    "weight": item.get("weight_kg", 0.5),
                }
                for item in items
            ],
            "route_points": [
                {
                    "point_id": 1,
                    "visit_order": 1,
                    "type": "source",
                    "address": {
                        "fullname": pickup_address,
                        "coordinates": [pickup_lon, pickup_lat],
                    },
                    "contact": {
                        "name": pickup_name,
                        "phone": pickup_phone,
                    },
                },
                {
                    "point_id": 2,
                    "visit_order": 2,
                    "type": "destination",
                    "address": {
                        "fullname": dropoff_address,
                        "coordinates": [dropoff_lon, dropoff_lat],
                    },
                    "contact": {
                        "name": dropoff_name,
                        "phone": dropoff_phone,
                    },
                },
            ],
            "skip_door_to_door": False,
            "comment": comment or "",
        }

        request_id = str(uuid.uuid4())
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{self.base_url}/claims/create",
                params={"request_id": request_id},
                headers=self._headers(),
                json=payload,
            )
            if r.status_code >= 400:
                raise YandexDeliveryError(f"Claim yaratishda xato: {r.status_code} {r.text}")
            data = r.json()

        return {
            "id": data.get("id"),
            "status": data.get("status"),
            "tracking_url": data.get("pricing", {}).get("tracking_url"),
            "price": float(data.get("pricing", {}).get("offer", {}).get("price", 0) or 0),
        }

    async def accept_claim(self, claim_id: str) -> dict:
        """Claim ni tasdiqlash — kuryer qidirish boshlanadi."""
        if self.mock_mode:
            return {"id": claim_id, "status": "accepted"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/claims/accept",
                params={"claim_id": claim_id},
                headers=self._headers(),
                json={"version": 1},
            )
            if r.status_code >= 400:
                raise YandexDeliveryError(f"Claim accept xato: {r.status_code} {r.text}")
            return r.json()

    async def get_claim_info(self, claim_id: str) -> dict:
        """Claim haqida ma'lumot olish."""
        if self.mock_mode:
            return {"id": claim_id, "status": "performer_found"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/claims/info",
                params={"claim_id": claim_id},
                headers=self._headers(),
            )
            if r.status_code >= 400:
                raise YandexDeliveryError(f"Claim info xato: {r.status_code}")
            return r.json()

    async def cancel_claim(self, claim_id: str, reason: str = "client_wants_other") -> dict:
        """Claim ni bekor qilish."""
        if self.mock_mode:
            return {"id": claim_id, "status": "cancelled"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/claims/cancel",
                params={"claim_id": claim_id},
                headers=self._headers(),
                json={"version": 1, "cancel_state": "free"},
            )
            if r.status_code >= 400:
                raise YandexDeliveryError(f"Claim cancel xato: {r.status_code}")
            return r.json()

    def _mock_create_claim(self, items: list[dict], total_price: float) -> dict:
        """Test uchun — haqiqiy API chaqirmasdan muvaffaqiyatli javob qaytarish."""
        claim_id = f"mock-{uuid.uuid4().hex[:12]}"
        # Taxminiy narx: 15,000 so'm boshlang'ich
        mock_price = 15000.0
        return {
            "id": claim_id,
            "status": "new",
            "tracking_url": f"https://dostavka.yandex.uz/track/{claim_id}",
            "price": mock_price,
        }
