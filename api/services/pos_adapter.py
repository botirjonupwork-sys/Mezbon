"""Hybrid Connect — universal POS / Printer adapter.

Restoran uchun tanlangan `pos_system_type` ga qarab, buyurtmani tegishli
drayverga yo'naltiradi. Har bir drayver bitta interfeysga (`POSDriver`)
amal qiladi va `dispatch(order)` ni `bool` qaytaradi (muvaffaqiyat/xato).

Tashqi API yiqilsa — `log_critical` ga yoziladi va asosiy buyurtma
oqimi DAVOM ETADI (eng muhim qoida — chek bo'lmasa ham mijoz ovqat oladi).

Drayverlar:
    NeonAlisaDriver       — NeonAlisa Cloud API orqali fiskallashtirish
    GenericAndroidDriver  — WebSocket bridge orqali Android terminallarga signal
    BluetoothPrinterDriver — ESC/POS bytes generatsiya qiladi (klient tomonida chop)
    NoneDriver            — no-op (POS ulanmagan restoran)

WebSocket bridge: `POSAdapter.bridge` ga ulangan client'lar (Android-app yoki
agent kompyuter) `restaurant_id` bo'yicha guruhlanadi. `dispatch_order` shu
guruhga JSON push qiladi.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.logging_config import log_critical
from database.models import Order, OrderItem, Product, Restaurant


# ── POS turlari (Enum-like) ─────────────────────────────────────────────

POS_NONE = "NONE"
POS_NEONALISA = "NEONALISA"
POS_GENERIC_ANDROID = "GENERIC_ANDROID"
POS_BLUETOOTH_PRINTER = "BLUETOOTH_PRINTER"

POS_TYPES = (POS_NONE, POS_NEONALISA, POS_GENERIC_ANDROID, POS_BLUETOOTH_PRINTER)


# ── Universal Order Schema ──────────────────────────────────────────────

@dataclass
class UniversalOrderItem:
    product_id: int
    name: str
    quantity: int
    price_uzs: float
    total_uzs: float


@dataclass
class UniversalOrder:
    """POS-agnostic buyurtma. Har drayver shu schema'ni qabul qiladi."""
    order_id: int
    restaurant_id: int
    items: list[UniversalOrderItem]
    subtotal_uzs: float
    delivery_fee_uzs: float
    total_uzs: float
    fiscal_flag: bool                       # True bo'lsa fiskal chek talab qilinadi
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    delivery_address: Optional[str] = None
    payment_method: str = "cash"            # 'cash' | 'card'
    comment: Optional[str] = None
    created_at_iso: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ── Order → Universal mapper ────────────────────────────────────────────

async def build_universal_order(
    db: AsyncSession, order: Order, *, fiscal: bool = True,
) -> UniversalOrder:
    """`Order` modelini Universal schemaga o'tkazadi.

    `order.items`'ni eager-load qiladi (agar kerak bo'lsa).
    """
    if not order.items:
        re_res = await db.execute(
            select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
        )
        order = re_res.scalar_one()

    items: list[UniversalOrderItem] = []
    for it in order.items:
        # Mahsulot nomini olish (ko'p hollarda kerak)
        prod_res = await db.execute(select(Product).where(Product.id == it.product_id))
        p = prod_res.scalar_one_or_none()
        items.append(UniversalOrderItem(
            product_id=it.product_id,
            name=p.name_uz if p else f"#{it.product_id}",
            quantity=int(it.quantity),
            price_uzs=float(it.price),
            total_uzs=float(it.price) * int(it.quantity),
        ))

    return UniversalOrder(
        order_id=order.id,
        restaurant_id=order.restaurant_id,
        items=items,
        subtotal_uzs=float(order.total_price or 0),
        delivery_fee_uzs=float(order.delivery_fee or 0),
        total_uzs=float(order.total_price or 0) + float(order.delivery_fee or 0),
        fiscal_flag=fiscal,
        delivery_address=order.address,
        payment_method=order.payment_method or "cash",
        comment=order.comment,
        created_at_iso=order.created_at.isoformat() if order.created_at else None,
    )


# ── ESC/POS generator ──────────────────────────────────────────────────
# Oddiy chek printerlari uchun raw text formati. Bytes qaytaradi.
# Bu modulda biz chop qilmaymiz — faqat to'g'ri bytes tayyorlaymiz.
# Klient (Android app yoki desktop agent) shu bytes'ni printerga oqim qiladi.

_ESC = b"\x1b"
_GS = b"\x1d"
_INIT = _ESC + b"@"
_ALIGN_CENTER = _ESC + b"a\x01"
_ALIGN_LEFT = _ESC + b"a\x00"
_BOLD_ON = _ESC + b"E\x01"
_BOLD_OFF = _ESC + b"E\x00"
_DOUBLE_HEIGHT = _GS + b"!\x01"
_NORMAL_SIZE = _GS + b"!\x00"
_CUT = _GS + b"V\x42\x00"
_NEWLINE = b"\n"


def _enc(s: str) -> bytes:
    """CP866 yoki CP1251 — oddiy printerlar uchun. UTF-8 ko'p modellarda yaxshi ishlaydi."""
    try:
        return s.encode("utf-8")
    except UnicodeEncodeError:
        return s.encode("ascii", errors="replace")


def generate_escpos(uo: UniversalOrder, restaurant_name: str = "") -> bytes:
    """Universal Order → ESC/POS raw bytes (58mm yoki 80mm printer uchun)."""
    out = bytearray()
    out += _INIT
    out += _ALIGN_CENTER + _BOLD_ON + _DOUBLE_HEIGHT
    if restaurant_name:
        out += _enc(restaurant_name) + _NEWLINE
    out += _NORMAL_SIZE + _BOLD_OFF
    out += _enc(f"Buyurtma #{uo.order_id}") + _NEWLINE
    if uo.created_at_iso:
        out += _enc(uo.created_at_iso[:19].replace("T", " ")) + _NEWLINE
    out += _enc("-" * 32) + _NEWLINE

    out += _ALIGN_LEFT
    for it in uo.items:
        out += _enc(f"{it.name}") + _NEWLINE
        out += _enc(f"  {it.quantity} x {int(it.price_uzs):,} = {int(it.total_uzs):,}") + _NEWLINE

    out += _enc("-" * 32) + _NEWLINE
    if uo.delivery_fee_uzs:
        out += _enc(f"Yetkazib berish: {int(uo.delivery_fee_uzs):,}") + _NEWLINE
    out += _BOLD_ON + _enc(f"JAMI: {int(uo.total_uzs):,} so'm") + _BOLD_OFF + _NEWLINE
    out += _enc(f"To'lov: {uo.payment_method.upper()}") + _NEWLINE

    if uo.delivery_address:
        out += _enc("-" * 32) + _NEWLINE
        out += _enc(f"Manzil: {uo.delivery_address[:64]}") + _NEWLINE
    if uo.comment:
        out += _enc(f"Izoh: {uo.comment[:64]}") + _NEWLINE

    out += _NEWLINE * 4 + _CUT
    return bytes(out)


# ── WebSocket bridge ───────────────────────────────────────────────────
# API'ga ega bo'lmagan terminallar (Android tablet, kassa kompyuteri) bizga
# WebSocket orqali ulanadi va keladigan signal'larni listening turadi.

class WebSocketBridge:
    """Restoran ID bo'yicha ulangan client'larni saqlovchi in-memory bridge."""

    def __init__(self) -> None:
        self._clients: dict[int, list[Any]] = {}   # restaurant_id -> [WebSocket]
        self._lock = asyncio.Lock()

    async def connect(self, restaurant_id: int, websocket) -> None:
        async with self._lock:
            self._clients.setdefault(restaurant_id, []).append(websocket)

    async def disconnect(self, restaurant_id: int, websocket) -> None:
        async with self._lock:
            if restaurant_id in self._clients:
                try:
                    self._clients[restaurant_id].remove(websocket)
                except ValueError:
                    pass

    async def broadcast(self, restaurant_id: int, payload: dict) -> int:
        """Restoranga ulangan barcha terminallarga payload yuboradi.

        Qaytaradi: muvaffaqiyatli yetkazilgan client'lar soni.
        Yiqilgan client'lar avtomatik o'chiriladi.
        """
        async with self._lock:
            clients = list(self._clients.get(restaurant_id, []))
        if not clients:
            return 0
        delivered = 0
        dead: list[Any] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
                delivered += 1
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                bucket = self._clients.get(restaurant_id, [])
                for d in dead:
                    try:
                        bucket.remove(d)
                    except ValueError:
                        pass
        return delivered

    def client_count(self, restaurant_id: int) -> int:
        return len(self._clients.get(restaurant_id, []))


bridge = WebSocketBridge()


# ── Drayverlar ─────────────────────────────────────────────────────────

class POSDriver:
    """Drayver interfeysi."""
    name: str = "base"

    async def dispatch(self, uo: UniversalOrder, restaurant: Restaurant) -> dict:
        raise NotImplementedError

    async def test_print(self, restaurant: Restaurant) -> dict:
        """Test chop — restoranga ulanishni tekshirish uchun."""
        sample = UniversalOrder(
            order_id=0, restaurant_id=restaurant.id,
            items=[UniversalOrderItem(0, "Salom Dunyo (Test)", 1, 1000, 1000)],
            subtotal_uzs=1000, delivery_fee_uzs=0, total_uzs=1000,
            fiscal_flag=False, comment="Test print",
            created_at_iso=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        return await self.dispatch(sample, restaurant)


class NoneDriver(POSDriver):
    """POS ulanmagan — hech narsa qilinmaydi."""
    name = "none"

    async def dispatch(self, uo: UniversalOrder, restaurant: Restaurant) -> dict:
        return {"ok": True, "driver": self.name, "delivered": 0, "skipped": True}


class NeonAlisaDriver(POSDriver):
    """NeonAlisa Cloud API orqali fiskal chek va kassaga yuborish."""
    name = "neonalisa"

    DEFAULT_BASE_URL = "https://api.neonalisa.uz/v1"
    TIMEOUT = 10.0

    async def dispatch(self, uo: UniversalOrder, restaurant: Restaurant) -> dict:
        cfg = restaurant.pos_config or {}
        api_key = (cfg.get("api_key") or "").strip()
        merchant_id = (cfg.get("merchant_id") or "").strip()
        base_url = (cfg.get("base_url") or self.DEFAULT_BASE_URL).rstrip("/")

        if not api_key or not merchant_id:
            log_critical(
                "pos", "NeonAlisa: api_key/merchant_id sozlanmagan",
                restaurant_id=restaurant.id, order_id=uo.order_id,
            )
            return {"ok": False, "driver": self.name, "error": "not_configured"}

        payload = {
            "merchant_id": merchant_id,
            "external_order_id": str(uo.order_id),
            "fiscal": uo.fiscal_flag,
            "total_uzs": uo.total_uzs,
            "items": [
                {"name": i.name, "qty": i.quantity, "price": i.price_uzs}
                for i in uo.items
            ],
            "payment_method": uo.payment_method,
            "comment": uo.comment,
        }
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                r = await client.post(
                    f"{base_url}/orders",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
            if 200 <= r.status_code < 300:
                data = {}
                try:
                    data = r.json()
                except Exception:
                    pass
                return {
                    "ok": True, "driver": self.name,
                    "neon_id": data.get("id"),
                    "fiscal_qr": data.get("fiscal_qr"),
                }
            log_critical(
                "pos", "NeonAlisa: HTTP xato",
                http_code=r.status_code, restaurant_id=restaurant.id,
                order_id=uo.order_id, body=r.text[:300],
            )
            return {"ok": False, "driver": self.name, "http_code": r.status_code}
        except httpx.TimeoutException:
            log_critical(
                "pos", "NeonAlisa: timeout",
                restaurant_id=restaurant.id, order_id=uo.order_id,
            )
            return {"ok": False, "driver": self.name, "error": "timeout"}
        except Exception as e:
            log_critical(
                "pos", "NeonAlisa: kutilmagan xato", error=str(e),
                restaurant_id=restaurant.id, order_id=uo.order_id,
            )
            return {"ok": False, "driver": self.name, "error": str(e)}


class GenericAndroidDriver(POSDriver):
    """API'ga ega bo'lmagan Android terminallar — WebSocket signal yuboradi."""
    name = "generic_android"

    async def dispatch(self, uo: UniversalOrder, restaurant: Restaurant) -> dict:
        payload = {
            "type": "print_order",
            "order": uo.to_dict(),
            "restaurant_name": restaurant.name,
        }
        delivered = await bridge.broadcast(restaurant.id, payload)
        if delivered == 0:
            log_critical(
                "pos", "Generic Android: hech qaysi terminal ulanmagan",
                restaurant_id=restaurant.id, order_id=uo.order_id,
            )
            return {"ok": False, "driver": self.name, "delivered": 0, "error": "no_terminals"}
        return {"ok": True, "driver": self.name, "delivered": delivered}


class BluetoothPrinterDriver(POSDriver):
    """Bluetooth chek printeri — ESC/POS bytes generatsiya qiladi va WebSocket'ga yuboradi.

    Sababi: server Bluetooth'ga to'g'ridan-to'g'ri ulana olmaydi, faqat
    restorandagi mobil ilova/agent qiladi. Biz unga bytes oqimini beramiz.
    """
    name = "bluetooth_printer"

    async def dispatch(self, uo: UniversalOrder, restaurant: Restaurant) -> dict:
        cfg = restaurant.pos_config or {}
        printer_mac = (cfg.get("printer_mac") or "").strip()
        if not printer_mac:
            log_critical(
                "pos", "Bluetooth: printer_mac sozlanmagan",
                restaurant_id=restaurant.id, order_id=uo.order_id,
            )
            return {"ok": False, "driver": self.name, "error": "not_configured"}

        bytes_payload = generate_escpos(uo, restaurant_name=restaurant.name)
        payload = {
            "type": "print_escpos",
            "printer_mac": printer_mac,
            # base64 bo'lmasdan json safe array (bytes JSON'ga sig'maydi)
            "escpos_b64": __import__("base64").b64encode(bytes_payload).decode("ascii"),
            "order_id": uo.order_id,
        }
        delivered = await bridge.broadcast(restaurant.id, payload)
        if delivered == 0:
            log_critical(
                "pos", "Bluetooth: agent ulanmagan",
                restaurant_id=restaurant.id, order_id=uo.order_id,
                printer_mac=printer_mac,
            )
            return {"ok": False, "driver": self.name, "delivered": 0, "error": "no_agent"}
        return {"ok": True, "driver": self.name, "delivered": delivered, "bytes": len(bytes_payload)}


# ── Adapter (router) ───────────────────────────────────────────────────

class POSAdapter:
    """Restoranning `pos_system_type` ga qarab tegishli drayverga yo'naltiradi."""

    def __init__(self) -> None:
        self.drivers: dict[str, POSDriver] = {
            POS_NONE: NoneDriver(),
            POS_NEONALISA: NeonAlisaDriver(),
            POS_GENERIC_ANDROID: GenericAndroidDriver(),
            POS_BLUETOOTH_PRINTER: BluetoothPrinterDriver(),
        }
        self.bridge = bridge

    def driver_for(self, restaurant: Restaurant) -> POSDriver:
        kind = (restaurant.pos_system_type or POS_NONE).upper()
        return self.drivers.get(kind, self.drivers[POS_NONE])

    async def dispatch_order(self, db: AsyncSession, order: Order) -> dict:
        """Tasdiqlangan buyurtmani POS'ga jo'natadi.

        Hech qachon exception ko'tarmaydi — xatolar `log_critical` ga yoziladi.
        Buyurtma oqimini halaqit bermaslik uchun bu funksiyani odatda
        `asyncio.create_task` ichida chaqiring.

        Faza 6: muvaffaqiyatli dispatch'da fiskal QR va receipt ID Order'ga
        yoziladi (mijozga chek yuborish uchun).
        """
        try:
            rest_res = await db.execute(
                select(Restaurant).where(Restaurant.id == order.restaurant_id)
            )
            rest = rest_res.scalar_one_or_none()
            if not rest:
                log_critical(
                    "pos", "Restoran topilmadi (dispatch_order)",
                    order_id=order.id, restaurant_id=order.restaurant_id,
                )
                return {"ok": False, "error": "restaurant_not_found"}

            uo = await build_universal_order(db, order, fiscal=True)
            driver = self.driver_for(rest)
            result = await driver.dispatch(uo, rest)

            # Faza 6: fiskal ma'lumotlarni Order'ga saqlash
            if result.get("ok"):
                fq = result.get("fiscal_qr")
                rid = result.get("neon_id") or result.get("receipt_id")
                if fq or rid:
                    if fq:
                        order.fiscal_qr = fq
                    if rid:
                        order.fiscal_receipt_id = str(rid)
                    await db.commit()
            return result
        except Exception as e:
            log_critical(
                "pos", "POSAdapter ichki xato", error=str(e),
                order_id=getattr(order, "id", None),
            )
            return {"ok": False, "error": str(e)}

    async def test_print(self, db: AsyncSession, restaurant_id: int) -> dict:
        rest_res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
        rest = rest_res.scalar_one_or_none()
        if not rest:
            return {"ok": False, "error": "restaurant_not_found"}
        driver = self.driver_for(rest)
        return await driver.test_print(rest)


# Global adapter instance
adapter = POSAdapter()
