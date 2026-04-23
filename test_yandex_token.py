"""Yandex Delivery token sinov skripti — narx hisoblash orqali tokenni tekshiradi."""
import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("YANDEX_DELIVERY_TOKEN", "")
TEST_MODE = os.getenv("YANDEX_DELIVERY_TEST_MODE", "True").lower() == "true"

BASE = "https://b2b.taxi.tst.yandex.net" if TEST_MODE else "https://b2b.taxi.yandex.net"
URL = f"{BASE}/b2b/cargo/integration/v2/check-price"

# Toshkent — Amir Temur ko'chasi → Chilonzor (test koordinatalari)
payload = {
    "items": [{"quantity": 1, "size": {"length": 0.2, "width": 0.2, "height": 0.1}, "weight": 1.0}],
    "route_points": [
        {"coordinates": [69.279737, 41.311081]},
        {"coordinates": [69.203448, 41.275143]},
    ],
    "skip_door_to_door": False,
    "requirements": {"taxi_class": "express"},
}


async def main():
    print(f"🔧 Mode: {'TEST' if TEST_MODE else 'PROD'}")
    print(f"🔑 Token: {TOKEN[:20]}...{TOKEN[-6:]}")
    print(f"🌐 URL: {URL}\n")

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept-Language": "ru",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(URL, headers=headers, json=payload)
        print(f"📡 HTTP {r.status_code}")
        print(f"📦 Response:\n{r.text[:1500]}")
        if r.status_code == 200:
            print("\n✅ TOKEN ISHLAYAPTI!")
        elif r.status_code == 401:
            print("\n❌ Token noto'g'ri yoki muddati tugagan")
        elif r.status_code == 403:
            print("\n⚠️ Token to'g'ri, lekin ruxsat yo'q (kompaniya ulanmagan/tasdiqlanmagan)")
        else:
            print(f"\n⚠️ Boshqa xato: {r.status_code}")


if __name__ == "__main__":
    asyncio.run(main())
