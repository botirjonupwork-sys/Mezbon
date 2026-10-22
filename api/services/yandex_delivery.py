"""Yandex Delivery B2B Cargo API client — Express v2.

API docs:
  - Overview:      https://yandex.com/support/delivery-profile/en/api/express/
  - OpenAPI:       https://yandex.com/dev/logistics/api/ref/express/
  - Status model:  https://yandex.com/support/delivery-profile/en/api/express/claim-process

Muhim eslatmalar (real API tekshirildi 2026-05):
  * Faqat bitta host bor — sandbox host mavjud emas. `test_mode` lokal `mock_mode`
    sifatida ishlatiladi (haqiqiy API'ga so'rov yuborilmaydi).
  * `droppof_point` Yandex schemasidagi typo — bu xato emas. Schemada shunday.
  * `coordinates` formati: [longitude, latitude] (lon birinchi!)
  * `cost_value` — decimal string (kopeyka emas)
  * Webhook GET so'rovi, body yo'q — faqat ?claim_id=X&updated_ts=Y query param.
    callback_url URL'ida `?` belgisi bo'lishi shart — Yandex faqat append qiladi.
"""
import httpx
import uuid
import logging
from decimal import Decimal
from typing import Optional


PROD_URL = "https://b2b.taxi.yandex.net/b2b/cargo/integration/v2"

log = logging.getLogger(__name__)


class YandexDeliveryError(Exception):
    pass


def _money(v) -> str:
    """Decimal string format Yandex'ga (e.g. 12345 → '12345.00')."""
    if v is None:
        return "0.00"
    return f"{Decimal(str(v)):.2f}"


class YandexDeliveryClient:
    """Yandex Delivery B2B Cargo Express v2 client.

    Sandbox host mavjud emas, shuning uchun `test_mode=True` faqat ichki
    mock rejimini bildiradi (haqiqiy so'rov yuborilmaydi). Token bo'sh bo'lsa
    ham mock ishlatiladi.
    """

    def __init__(self, api_token: str, test_mode: bool = True):
        self.api_token = api_token
        self.base_url = PROD_URL
        # Mock rejimi: token yo'q yoki test_mode yoqilgan.
        self.mock_mode = (not api_token) or api_token in ("test", "mock") or bool(test_mode)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept-Language": "ru",
            "Content-Type": "application/json",
        }

    # ── Create claim ────────────────────────────────────────────────────

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
        callback_url: Optional[str] = None,
        emergency_phone: Optional[str] = None,
        taxi_class: str = "courier",
        cost_currency: str = "UZS",
        request_id: Optional[str] = None,
        due: Optional[str] = None,
    ) -> dict:
        """Yandex'ga dastavka so'rovi (claim) yaratish.

        items: [{title, quantity, cost_value, weight_kg?}, ...]
        callback_url: webhook olish manzili — `?token=...` bilan bo'lishi shart.
        emergency_phone: muammo bo'lganda bog'lanish raqami.
        request_id: idempotency UUID; takroriy yuborilsa Yandex bir xil claim qaytaradi.
        due: ISO 8601 — kuryerning A nuqtaga (pickup) kelish vaqti.
             Bo'sh bo'lsa — eng yaqin vaqtga qidiriladi.
             Vaqtli zakaz uchun majburiy (masalan '2026-07-14T12:30:00+05:00').

        Qaytaradi:
          {id, status, version, offer_id, price, request_id}
        """
        req_id = request_id or str(uuid.uuid4())

        if self.mock_mode:
            return self._mock_create_claim(req_id, total_price)

        # Items uchun manba/nishon point id (route_points dagi point_id ga to'g'ri keladi)
        api_items = []
        for it in items:
            api_items.append({
                "title": it["title"][:60],
                "quantity": int(it.get("quantity") or 1),
                "cost_value": _money(it.get("cost_value", 0)),
                "cost_currency": cost_currency,
                "weight": float(it.get("weight_kg") or 0.5),
                # ── Yandex schemasidagi typo — `droppof_point` (bu kerak)
                "pickup_point": 1,
                "droppof_point": 2,
            })

        payload = {
            "items": api_items,
            "route_points": [
                {
                    "point_id": 1,
                    "visit_order": 1,
                    "type": "source",
                    "address": {
                        "fullname": pickup_address,
                        "shortname": pickup_address[:60],
                        "coordinates": [pickup_lon, pickup_lat],  # [lon, lat]
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
                        "shortname": dropoff_address[:60],
                        "coordinates": [dropoff_lon, dropoff_lat],
                    },
                    "contact": {
                        "name": dropoff_name,
                        "phone": dropoff_phone,
                    },
                },
            ],
            "emergency_contact": {
                "name": pickup_name,
                "phone": emergency_phone or pickup_phone,
            },
            "client_requirements": {
                "taxi_class": taxi_class,  # courier | express | cargo
            },
            "skip_door_to_door": False,
            "comment": (comment or "")[:7000],
        }

        # Vaqtli zakaz — kuryer A nuqtaga shu vaqtda keladi
        if due:
            payload["due"] = due

        # Webhook URL — Yandex query parametrlarni append qiladi, `?` bo'lishi shart
        if callback_url:
            payload["callback_properties"] = {"callback_url": callback_url}

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{self.base_url}/claims/create",
                params={"request_id": req_id},
                headers=self._headers(),
                json=payload,
            )
            if r.status_code >= 400:
                log.error("Yandex create_claim %d: %s", r.status_code, r.text)
                raise YandexDeliveryError(f"Claim yaratishda xato: {r.status_code} {r.text[:300]}")
            data = r.json()

        pricing = data.get("pricing") or {}
        offer = pricing.get("offer") or {}
        return {
            "id": data.get("id"),
            "status": data.get("status"),
            "version": data.get("version", 1),
            "offer_id": offer.get("offer_id"),
            "price": float(offer.get("price") or pricing.get("currency_rules", {}).get("code") or 0),
            "request_id": req_id,
        }

    # ── Accept claim ────────────────────────────────────────────────────

    async def accept_claim(self, claim_id: str, version: int = 1) -> dict:
        """Claim'ni tasdiqlash — kuryer qidirish boshlanadi.

        DIQQAT: create_claim natijasidagi `version` bilan chaqirish kerak.
        Offer 10 daqiqada eskiradi — darhol chaqirilsin.
        """
        if self.mock_mode:
            return {"id": claim_id, "status": "accepted", "version": version + 1}

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/claims/accept",
                params={"claim_id": claim_id},
                headers=self._headers(),
                json={"version": int(version)},
            )
            if r.status_code >= 400:
                log.error("Yandex accept_claim %d: %s", r.status_code, r.text)
                raise YandexDeliveryError(f"Claim accept xato: {r.status_code} {r.text[:300]}")
            return r.json()

    # ── Get claim info ──────────────────────────────────────────────────

    async def get_claim_info(self, claim_id: str) -> dict:
        """Claim haqida joriy ma'lumot (status, performer, eta, narx).

        Webhook bizga faqat `claim_id` yuboradi — status va boshqa
        ma'lumotni shu metod orqali olamiz.
        """
        if self.mock_mode:
            return {
                "id": claim_id,
                "status": "performer_found",
                "version": 2,
                "performer_info": {
                    "courier_name": "Test Kuryer",
                    "car_model": "Cobalt",
                    "car_number": "01A123BC",
                },
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/claims/info",
                params={"claim_id": claim_id},
                headers=self._headers(),
                json={},
            )
            if r.status_code >= 400:
                log.error("Yandex claim_info %d: %s", r.status_code, r.text)
                raise YandexDeliveryError(f"Claim info xato: {r.status_code}")
            return r.json()

    # ── Tracking link ───────────────────────────────────────────────────

    async def get_tracking_link(self, claim_id: str) -> Optional[str]:
        """Mijoz uchun kuzatish URL'i (destination point uchun)."""
        if self.mock_mode:
            return f"https://dostavka.yandex.uz/track/{claim_id}"

        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{self.base_url}/claims/tracking-links",
                params={"claim_id": claim_id},
                headers=self._headers(),
            )
            if r.status_code >= 400:
                log.warning("Yandex tracking_link %d: %s", r.status_code, r.text)
                return None
            data = r.json() or {}
            for rp in (data.get("route_points") or []):
                if rp.get("type") == "destination":
                    link = rp.get("sharing_link")
                    if link:
                        return link
        return None

    # ── Cancel claim ────────────────────────────────────────────────────

    async def cancel_claim(self, claim_id: str, version: int = 1, cancel_state: str = "free") -> dict:
        """Claim bekor qilish.

        cancel_state:
          - "free" — kuryer hali pickup'ga yo'l olmagan (bepul)
          - "paid" — yo'lda yoki yetib kelgan (to'lov ushlab qolinadi)

        Avval `cancel_info` bilan qaysi rejim mavjudligini tekshirish tavsiya etiladi.
        """
        if self.mock_mode:
            return {"id": claim_id, "status": "cancelled", "version": version + 1}

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{self.base_url}/claims/cancel",
                params={"claim_id": claim_id},
                headers=self._headers(),
                json={"version": int(version), "cancel_state": cancel_state},
            )
            if r.status_code >= 400:
                log.error("Yandex cancel_claim %d: %s", r.status_code, r.text)
                raise YandexDeliveryError(f"Claim cancel xato: {r.status_code} {r.text[:300]}")
            return r.json()

    async def cancel_info(self, claim_id: str) -> dict:
        """Qaysi cancel_state mavjudligini tekshirish (`free` yoki `paid`)."""
        if self.mock_mode:
            return {"cancel_state": "free"}

        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                f"{self.base_url}/claims/cancel-info",
                params={"claim_id": claim_id},
                headers=self._headers(),
                json={},
            )
            if r.status_code >= 400:
                return {"cancel_state": "free"}
            return r.json() or {"cancel_state": "free"}

    # ── Mock ────────────────────────────────────────────────────────────

    def _mock_create_claim(self, request_id: str, total_price: float) -> dict:
        """Test rejimi: haqiqiy API chaqirmasdan claim yaratilganini taqlid qilamiz."""
        claim_id = f"mock-{uuid.uuid4().hex[:12]}"
        return {
            "id": claim_id,
            "status": "new",
            "version": 1,
            "offer_id": f"offer-{uuid.uuid4().hex[:8]}",
            "price": 25000.0,
            "request_id": request_id,
        }

    async def quote_price(
        self,
        *,
        pickup_lat: float,
        pickup_lon: float,
        dropoff_lat: float,
        dropoff_lon: float,
        weight_kg: float = 1.0,
        taxi_class: str = "courier",
        due: Optional[str] = None,
    ) -> dict:
        """Faqat narx hisoblash — claim YARATMAYDI, restoran balansidan pul KETMAYDI.

        taxi_class: claim yaratish bilan BIR XIL bo'lishi kerak (default 'courier').
        'express' sezilarli qimmatroq — quote'da ishlatilmasin.
        due: ISO 8601 — vaqtli yetkazish uchun (ixtiyoriy).

        Qaytaradi:
          {"ok": True, "price": 18200.0, "currency": "UZS", "eta_minutes": 25}
          yoki
          {"ok": False, "code": "no_coverage" | "no_offer" | "error", "message": "..."}
        """
        if self.mock_mode:
            return {"ok": True, "price": 18000.0, "currency": "UZS", "eta_minutes": 20, "mock": True}

        # Faqat Yandex qabul qiladigan klasslar
        tc = (taxi_class or "courier").strip().lower()
        if tc not in ("courier", "express", "cargo"):
            tc = "courier"

        requirements: dict = {"taxi_class": tc}
        if due:
            requirements["due"] = due

        payload = {
            "items": [{
                "quantity": 1,
                "size": {"length": 0.3, "width": 0.2, "height": 0.15},
                "weight": float(weight_kg or 1.0),
            }],
            "route_points": [
                {"coordinates": [float(pickup_lon), float(pickup_lat)]},
                {"coordinates": [float(dropoff_lon), float(dropoff_lat)]},
            ],
            "skip_door_to_door": False,
            "requirements": requirements,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{self.base_url}/check-price",
                    headers=self._headers(),
                    json=payload,
                )
        except Exception as e:
            log.warning("Yandex quote_price network error: %s", e)
            return {"ok": False, "code": "network_error", "message": str(e)}

        if r.status_code == 200:
            try:
                d = r.json()
            except Exception:
                return {"ok": False, "code": "bad_response", "message": r.text[:200]}
            price = d.get("price") or d.get("price_raw") or 0
            return {
                "ok": True,
                "price": float(price),
                "currency": d.get("currency_rules", {}).get("code", "UZS"),
                "eta_minutes": int(d.get("eta") or 0) or None,
            }

        # 409 — coverage / no available offer
        if r.status_code == 409:
            try:
                d = r.json()
                code = (d.get("code") or "").lower()
            except Exception:
                code = ""
            return {
                "ok": False,
                "code": "no_coverage" if "not_found" in code or "suitable" in code else "no_offer",
                "message": "Bu manzilga hozir Yandex kuryeri yo'q",
            }

        log.warning("Yandex quote_price %d: %s", r.status_code, r.text[:200])
        return {
            "ok": False,
            "code": "error",
            "message": f"HTTP {r.status_code}: {r.text[:200]}",
        }
