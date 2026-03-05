import httpx
from typing import Optional
from api.config import settings


class AlicePOS:
    """Alice POS REST API v2 integratsiyasi"""

    def __init__(self):
        self.base_url = settings.ALICE_API_URL
        self.api_key = settings.ALICE_API_KEY
        self.store_id = settings.ALICE_STORE_ID

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def get_products(self) -> list:
        """Alice POS dan barcha mahsulotlarni olish"""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.base_url}/stores/{self.store_id}/products",
                headers=self.headers,
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def get_categories(self) -> list:
        """Kategoriyalarni olish"""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.base_url}/stores/{self.store_id}/categories",
                headers=self.headers,
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

    async def create_order(self, order_data: dict) -> dict:
        """Alice POS da yangi zakaz yaratish"""
        payload = {
            "store_id": self.store_id,
            "items": order_data["items"],
            "customer": {
                "name": order_data["customer_name"],
                "phone": order_data["customer_phone"],
            },
            "note": order_data.get("comment", ""),
            "delivery_type": order_data["delivery_type"],
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base_url}/orders",
                headers=self.headers,
                json=payload,
                timeout=15,
            )
            r.raise_for_status()
            return r.json()

    async def get_order_status(self, alice_order_id: str) -> Optional[str]:
        """Zakaz holatini tekshirish"""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.base_url}/orders/{alice_order_id}",
                headers=self.headers,
                timeout=10,
            )
            if r.status_code == 200:
                return r.json().get("status")
            return None

    async def sync_products_to_db(self, db_session) -> int:
        """Alice POS dan mahsulotlarni DB ga sinxronlashtirish (tuzatilgan)"""
        from database.models import Product, Category
        from sqlalchemy import select

        products = await self.get_products()
        categories = await self.get_categories()

        # Kategoriyalarni yangilash
        for cat in categories:
            result = await db_session.execute(
                select(Category).where(Category.alice_category_id == str(cat["id"]))
            )
            if not result.scalar_one_or_none():
                db_session.add(Category(
                    alice_category_id=str(cat["id"]),
                    name_uz=cat.get("name", ""),
                    name_ru=cat.get("name", ""),
                ))

        await db_session.flush()

        # Mahsulotlarni yangilash
        for product in products:
            result = await db_session.execute(
                select(Product).where(Product.alice_product_id == str(product["id"]))
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.price = product.get("price", existing.price)
                existing.name_uz = product.get("name", existing.name_uz)
            else:
                db_session.add(Product(
                    alice_product_id=str(product["id"]),
                    name_uz=product.get("name", ""),
                    price=float(product.get("price", 0)),
                    is_active=product.get("active", True),
                ))

        await db_session.commit()
        return len(products)


alice_pos = AlicePOS()
