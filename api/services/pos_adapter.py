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
import base64
import json
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.logging_config import log_critical
from database.models import Branch, Order, OrderItem, Product, Restaurant, User


# ── POS turlari (Enum-like) ─────────────────────────────────────────────

POS_NONE = "NONE"
POS_NEONALISA = "NEONALISA"
POS_GENERIC_ANDROID = "GENERIC_ANDROID"
POS_BLUETOOTH_PRINTER = "BLUETOOTH_PRINTER"
POS_LAN_PRINTER = "LAN_PRINTER"   # Tarmoq (Ethernet/IP) chek printeri — Xprinter va h.k.

POS_TYPES = (POS_NONE, POS_NEONALISA, POS_GENERIC_ANDROID, POS_BLUETOOTH_PRINTER, POS_LAN_PRINTER)


# ── Universal Order Schema ──────────────────────────────────────────────

@dataclass
class UniversalOrderItem:
    product_id: int
    name: str
    quantity: int
    price_uzs: float
    total_uzs: float
    category_id: Optional[int] = None   # stansiya bo'yicha yo'naltirish uchun


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
    payment_method: str = "cash"            # 'cash' | 'card' | 'click' | 'payme' | 'uzum'
    payment_status: Optional[str] = None    # 'pending' | 'paid' | 'failed' | 'partial'
    paid_amount_uzs: float = 0
    comment: Optional[str] = None
    created_at_iso: Optional[str] = None
    branch_name: Optional[str] = None
    order_type: Optional[str] = None        # 'delivery' | 'pickup'
    vat_uzs: float = 0
    fiscal_qr: Optional[str] = None
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
            category_id=(p.category_id if p else None),
        ))

    # Mijoz (User) — ism va telefon
    cust_name = cust_phone = None
    if order.user_id:
        u_res = await db.execute(select(User).where(User.id == order.user_id))
        u = u_res.scalar_one_or_none()
        if u:
            cust_name = u.full_name
            cust_phone = u.phone

    # Filial nomi
    branch_name = None
    if order.branch_id:
        b_res = await db.execute(select(Branch).where(Branch.id == order.branch_id))
        b = b_res.scalar_one_or_none()
        if b:
            branch_name = b.name

    # Buyurtma turi — 'delivery' | 'pickup'
    try:
        order_type = order.delivery_type.value if order.delivery_type else (order.service_type or None)
    except Exception:
        order_type = order.service_type or None

    return UniversalOrder(
        order_id=order.id,
        restaurant_id=order.restaurant_id,
        items=items,
        subtotal_uzs=float(order.total_price or 0),
        delivery_fee_uzs=float(order.delivery_fee or 0),
        total_uzs=float(order.total_price or 0) + float(order.delivery_fee or 0),
        fiscal_flag=fiscal,
        customer_name=cust_name,
        customer_phone=cust_phone,
        delivery_address=order.address,
        payment_method=order.payment_method or "cash",
        payment_status=order.payment_status,
        paid_amount_uzs=float(order.paid_amount_tiyin or 0) / 100.0,
        comment=order.comment,
        created_at_iso=order.created_at.isoformat() if order.created_at else None,
        branch_name=branch_name,
        order_type=order_type,
        vat_uzs=float(order.vat_amount_tiyin or 0) / 100.0,
        fiscal_qr=order.fiscal_qr,
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


# To'lov turi / holati / buyurtma turi yorliqlari
_PAY_LABEL = {
    "cash": "Naqd pul", "card": "Karta", "click": "Karta (Click)",
    "payme": "Payme", "uzum": "Uzum",
}
_PAY_STATUS = {
    "paid": "TO'LANGAN", "pending": "KUTILMOQDA",
    "failed": "XATO", "partial": "QISMAN TO'LANGAN",
}
_OTYPE_LABEL = {"delivery": "Yetkazib berish", "pickup": "Olib ketish"}


def _money(n) -> str:
    """123456 -> '123 456' (so'm uchun probel ajratgich)."""
    return f"{int(round(float(n or 0))):,}".replace(",", " ")


def _row(label: str, value: str, width: int) -> str:
    """label chap, value o'ng chekkada; orasi probel bilan to'ldiriladi."""
    gap = width - len(label) - len(value)
    return label + (" " * gap if gap > 0 else " ") + value


def _field(label: str, value: str, lblw: int) -> str:
    """'Telefon:       +998...' — yorliq chapdan lblw ustunga tekislanadi."""
    return label.ljust(lblw) + str(value)


def _wrap(text: str, width: int) -> list[str]:
    """Uzun matnni so'zlar bo'yicha width belgidan oshmaydigan qatorlarga bo'ladi."""
    words = str(text).split()
    if not words:
        return []
    lines, cur = [], words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _qr(data: str) -> bytes:
    """ESC/POS QR kod (Model 2) — fiskal chek havolasi uchun."""
    d = data.encode("utf-8")
    n = len(d) + 3
    pL, pH = n % 256, n // 256
    b = bytearray()
    b += _GS + b"(k\x04\x00\x31\x41\x32\x00"           # model: 2
    b += _GS + b"(k\x03\x00\x31\x43\x06"               # modul o'lchami: 6
    b += _GS + b"(k\x03\x00\x31\x45\x31"               # xato tuzatish: M
    b += _GS + b"(k" + bytes([pL, pH]) + b"\x31\x50\x30" + d  # ma'lumotni saqlash
    b += _GS + b"(k\x03\x00\x31\x51\x30"               # chop etish
    return bytes(b)


def generate_escpos(
    uo: UniversalOrder,
    restaurant_name: str = "",
    station_name: str = "",
    width: int = 48,
    full: bool = True,
) -> bytes:
    """Universal Order → ESC/POS raw bytes (to'liq chek).

    width        — chek kengligi belgida (80mm = 48, 58mm = 32).
    full=True    — mijoz/kassa cheki (mijoz, to'lov, JAMI, QR bilan to'liq).
    full=False   — oshxona cheki (faqat mahsulotlar; pul/mijoz ko'rsatilmaydi).
    station_name — oshxona stansiyasi nomi; berilsa chek tepasida yirik chiqadi.
    """
    W = int(width or 48)
    LBL = 16  # ma'lumot yorliqlari uchun ustun kengligi
    RW = 21   # mahsulot qatorida soni/summa ustuni kengligi
    out = bytearray()
    out += _INIT

    # ── Sarlavha ──────────────────────────────────────────────────────────
    out += _ALIGN_CENTER
    if station_name:
        out += _BOLD_ON + _DOUBLE_HEIGHT + _enc(station_name.upper()) + _NEWLINE
        out += _NORMAL_SIZE + _BOLD_OFF
    if restaurant_name:
        out += _BOLD_ON + _DOUBLE_HEIGHT + _enc(restaurant_name) + _NEWLINE
        out += _NORMAL_SIZE + _BOLD_OFF
    out += _enc("Buyurtma cheki" if full else "Oshxona cheki") + _NEWLINE
    out += _enc("=" * W) + _NEWLINE
    out += _ALIGN_LEFT

    # ── Buyurtma ma'lumotlari ─────────────────────────────────────────────
    when = (uo.created_at_iso or "")[:16].replace("T", " ")
    out += _enc(_row(f"Buyurtma #{uo.order_id}", when, W)) + _NEWLINE
    if uo.order_type:
        out += _enc(_field("Turi:", _OTYPE_LABEL.get(uo.order_type, uo.order_type), LBL)) + _NEWLINE
    if uo.branch_name:
        out += _enc(_field("Filial:", uo.branch_name, LBL)) + _NEWLINE

    # ── Mijoz (faqat to'liq chekda) ───────────────────────────────────────
    if full and (uo.customer_name or uo.customer_phone or uo.delivery_address):
        out += _enc("-" * W) + _NEWLINE
        if uo.customer_name:
            out += _enc(_field("Mijoz:", uo.customer_name, LBL)) + _NEWLINE
        if uo.customer_phone:
            out += _enc(_field("Telefon:", uo.customer_phone, LBL)) + _NEWLINE
        if uo.delivery_address:
            alines = _wrap(uo.delivery_address, W - LBL) or [""]
            out += _enc(_field("Manzil:", alines[0], LBL)) + _NEWLINE
            for ln in alines[1:]:
                out += _enc(" " * LBL + ln) + _NEWLINE
        landmark = (uo.meta or {}).get("landmark")
        if landmark:
            out += _enc(_field("Mo'ljal:", landmark, LBL)) + _NEWLINE

    # ── Mahsulotlar ───────────────────────────────────────────────────────
    out += _enc("-" * W) + _NEWLINE
    items_subtotal = 0.0
    for it in uo.items:
        items_subtotal += float(it.total_uzs or 0)
        qtycol = f"{it.quantity}x{_money(it.price_uzs)}"
        rightblock = f"{qtycol:>10}{_money(it.total_uzs):>11}"  # 21 belgi
        name = it.name or ""
        if W >= 44 and len(name) + 1 + len(rightblock) <= W:
            out += _enc(_row(" " + name, rightblock, W)) + _NEWLINE
        else:
            for ln in _wrap(name, W - 1):
                out += _enc(" " + ln) + _NEWLINE
            out += _enc(_row("", rightblock, W)) + _NEWLINE

    # ── Yakuniy summalar ──────────────────────────────────────────────────
    out += _enc("-" * W) + _NEWLINE
    if not full:
        # Oshxona cheki — pulsiz, faqat mahsulotlar soni
        out += _enc(f" Jami: {len(uo.items)} ta mahsulot") + _NEWLINE
    else:
        out += _enc(_row(f" Mahsulotlar ({len(uo.items)} ta):", _money(items_subtotal), W)) + _NEWLINE
        if uo.delivery_fee_uzs:
            out += _enc(_row(" Yetkazib berish:", _money(uo.delivery_fee_uzs), W)) + _NEWLINE
        if uo.vat_uzs:
            out += _enc(_row(" QQS (12%):", _money(uo.vat_uzs), W)) + _NEWLINE
        out += _enc("-" * W) + _NEWLINE
        out += _BOLD_ON + _DOUBLE_HEIGHT
        out += _enc(_row(" JAMI:", f"{_money(uo.total_uzs)} so'm", W)) + _NEWLINE
        out += _NORMAL_SIZE + _BOLD_OFF
        out += _enc("-" * W) + _NEWLINE
        out += _enc(_field(" To'lov turi:", _PAY_LABEL.get(uo.payment_method, uo.payment_method), LBL)) + _NEWLINE
        if uo.payment_status:
            out += _enc(_field(" To'lov holati:", _PAY_STATUS.get(uo.payment_status, uo.payment_status), LBL)) + _NEWLINE
        if uo.paid_amount_uzs:
            out += _enc(_field(" To'langan:", f"{_money(uo.paid_amount_uzs)} so'm", LBL)) + _NEWLINE

    # ── Izoh ──────────────────────────────────────────────────────────────
    if uo.comment:
        out += _enc("-" * W) + _NEWLINE
        for ln in _wrap("Izoh: " + uo.comment, W):
            out += _enc(ln) + _NEWLINE

    # ── Footer + fiskal QR (faqat to'liq chekda) ──────────────────────────
    if full:
        out += _enc("-" * W) + _NEWLINE
        out += _ALIGN_CENTER
        out += _enc("Rahmat! Yana tashrif buyuring") + _NEWLINE
        out += _enc("Mezbon AI orqali buyurtma") + _NEWLINE
        if uo.fiscal_qr:
            out += _NEWLINE + _enc("Fiskal chek (QR):") + _NEWLINE
            out += _qr(uo.fiscal_qr) + _NEWLINE
        out += _ALIGN_LEFT
    out += _enc("=" * W) + _NEWLINE

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


class LANPrinterDriver(POSDriver):
    """Tarmoq (LAN/IP) chek printeri — Xprinter va boshqa ESC/POS printerlar.

    Server bulutda bo'lgani uchun restorandagi LAN printerga to'g'ridan-to'g'ri
    ula olmaydi. Shuning uchun ESC/POS bytes'ni WebSocket bridge orqali
    restorandagi agentga (kassa kompyuteridagi dastur) yuboramiz; agent uni
    printer IP:port (odatda 9100) ga TCP orqali oqim qiladi.
    """
    name = "lan_printer"

    @staticmethod
    def _valid_printers(cfg: dict) -> list[dict]:
        """pos_config['printers'] ro'yxatidan IP'si bor printerlarni qaytaradi."""
        printers = cfg.get("printers")
        if not isinstance(printers, list):
            return []
        return [p for p in printers if isinstance(p, dict) and (p.get("ip") or "").strip()]

    async def _send(self, restaurant: Restaurant, data: bytes, ip: str, port: int, order_id: int) -> int:
        payload = {
            "type": "print_escpos_tcp",
            "printer_ip": ip.strip(),
            "printer_port": int(port or 9100),
            "escpos_b64": base64.b64encode(data).decode("ascii"),
            "order_id": order_id,
        }
        return await bridge.broadcast(restaurant.id, payload)

    async def dispatch(self, uo: UniversalOrder, restaurant: Restaurant) -> dict:
        cfg = restaurant.pos_config or {}
        printers = self._valid_printers(cfg)

        # ── Ko'p stansiya ────────────────────────────────────────────────
        # Qoida: asosiy (default) printerga HAR DOIM to'liq mijoz cheki chiqadi
        # (kategoriya biriktirilmagan bo'lsa ham). Qo'shimcha stansiyalar —
        # faqat o'z kategoriyasidagi mahsulotlar uchun qisqa oshxona cheki.
        if printers:
            default_idx = next((i for i, p in enumerate(printers) if p.get("is_default")), 0)
            multi = len(printers) > 1
            total_delivered = 0
            stations = []

            def _cat_set(p: dict) -> set:
                raw = p.get("category_ids") or []
                out: set = set()
                for c in raw:
                    try:
                        out.add(int(c))
                    except (TypeError, ValueError):
                        continue
                return out

            for i, p in enumerate(printers):
                is_default = i == default_idx
                if is_default:
                    # Asosiy — har doim barcha mahsulotlar, to'liq chek
                    items_i = list(uo.items)
                    is_full = True
                    station_name = ""
                else:
                    cats = _cat_set(p)
                    if not cats:
                        continue  # stansiyaga kategoriya yo'q — o'tkazib yuboramiz
                    items_i = [
                        it for it in uo.items
                        if it.category_id is not None and int(it.category_id) in cats
                    ]
                    if not items_i:
                        continue
                    is_full = False
                    station_name = p.get("name") or ""

                if not items_i and not is_default:
                    continue

                sub = replace(uo, items=items_i) if (multi and not is_default) else uo
                data = generate_escpos(
                    sub, restaurant_name=restaurant.name,
                    station_name=station_name,
                    full=is_full,
                )
                delivered = await self._send(
                    restaurant, data, p["ip"], p.get("port") or 9100, uo.order_id,
                )
                total_delivered += delivered
                stations.append({
                    "printer": p.get("name"),
                    "items": len(items_i),
                    "delivered": delivered,
                    "default": is_default,
                })

            if total_delivered == 0:
                log_critical("pos", "LAN printer: agent ulanmagan (ko'p stansiya)",
                             restaurant_id=restaurant.id, order_id=uo.order_id)
                return {"ok": False, "driver": self.name, "delivered": 0,
                        "error": "no_agent", "stations": stations}
            return {"ok": True, "driver": self.name, "delivered": total_delivered, "stations": stations}

        # ── Eski yagona printer (orqaga moslik) ──────────────────────────
        printer_ip = (cfg.get("printer_ip") or "").strip()
        if not printer_ip:
            log_critical("pos", "LAN printer: sozlanmagan",
                         restaurant_id=restaurant.id, order_id=uo.order_id)
            return {"ok": False, "driver": self.name, "error": "not_configured"}
        data = generate_escpos(uo, restaurant_name=restaurant.name)
        delivered = await self._send(restaurant, data, printer_ip, cfg.get("printer_port") or 9100, uo.order_id)
        if delivered == 0:
            log_critical("pos", "LAN printer: agent ulanmagan",
                         restaurant_id=restaurant.id, order_id=uo.order_id, printer_ip=printer_ip)
            return {"ok": False, "driver": self.name, "delivered": 0, "error": "no_agent"}
        return {"ok": True, "driver": self.name, "delivered": delivered, "bytes": len(data)}

    async def test_print(self, restaurant: Restaurant) -> dict:
        """Har bir sozlangan printerga alohida test cheki yuboradi."""
        cfg = restaurant.pos_config or {}
        printers = self._valid_printers(cfg)
        if not printers:
            return await super().test_print(restaurant)

        test_uo = UniversalOrder(
            order_id=0, restaurant_id=restaurant.id,
            items=[UniversalOrderItem(product_id=0, name="TEST CHEK", quantity=1,
                                      price_uzs=0, total_uzs=0)],
            subtotal_uzs=0, delivery_fee_uzs=0, total_uzs=0,
            fiscal_flag=False, comment="Test print",
        )
        total = 0
        stations = []
        for p in printers:
            data = generate_escpos(test_uo, restaurant_name=restaurant.name,
                                   station_name=(p.get("name") or ""))
            delivered = await self._send(restaurant, data, p["ip"], p.get("port") or 9100, 0)
            total += delivered
            stations.append({"printer": p.get("name"), "delivered": delivered})
        return {"ok": total > 0, "driver": self.name, "delivered": total,
                "stations": stations, **({} if total > 0 else {"error": "no_agent"})}


# ── Adapter (router) ───────────────────────────────────────────────────

class POSAdapter:
    """Restoranning `pos_system_type` ga qarab tegishli drayverga yo'naltiradi."""

    def __init__(self) -> None:
        self.drivers: dict[str, POSDriver] = {
            POS_NONE: NoneDriver(),
            POS_NEONALISA: NeonAlisaDriver(),
            POS_GENERIC_ANDROID: GenericAndroidDriver(),
            POS_BLUETOOTH_PRINTER: BluetoothPrinterDriver(),
            POS_LAN_PRINTER: LANPrinterDriver(),
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
