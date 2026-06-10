"""Payme Subscribe API — karta tokenlashtirish + obunani avtomatik undirish.

Bu modul PLATFORMA (Mezbon) kassasi nomidan ishlaydi — restoran kassasi emas.
Restoran kartasi bir marta bog'lanadi (token olinadi), keyin har oy server tomonidan
avtomatik undiriladi. Webhook kerak emas — receipts.pay natijani sinxron qaytaradi.

Xavfsizlik:
  * Karta tokeni Fernet bilan SHIFRLANGAN holda DB'da saqlanadi (PaymeCard.token_enc).
    Master kalit env: PAYME_TOKEN_ENC_KEY (ma'lumotdan ajratilgan).
  * Karta RAQAMI hech qachon saqlanmaydi va loglanmaydi (faqat oxirgi 4 raqam).
  * Credential'lar platform_settings'dan olinadi (super-admin boshqaradi).

Rasmiy hujjat: developer.help.paycom.uz/protokol-subscribe-api/
  Endpoint: https://checkout.paycom.uz/api  (test: https://checkout.test.paycom.uz/api)
  X-Auth (cards.* mijoz tomoni):  "{merchant_id}"
  X-Auth (receipts.* + cards.check/remove server tomoni): "{merchant_id}:{key}"
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from api.config import settings
from api.services import platform

log = logging.getLogger(__name__)

_PROD_URL = "https://checkout.paycom.uz/api"
_TEST_URL = "https://checkout.test.paycom.uz/api"
_TIMEOUT = 20.0


# ── Token shifrlash (Fernet) ─────────────────────────────────────────

def _fernet():
    """PAYME_TOKEN_ENC_KEY asosida Fernet obyektini qaytaradi.

    Kalit yo'q bo'lsa aniq xato beramiz — token'ni shifrlamasdan saqlash taqiqlanadi.
    """
    key = (settings.PAYME_TOKEN_ENC_KEY or "").strip()
    if not key:
        raise PaymeSubscribeError(
            -1, "PAYME_TOKEN_ENC_KEY o'rnatilmagan — karta tokenini xavfsiz saqlab bo'lmaydi"
        )
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def encrypt_token(plain_token: str) -> str:
    """Ochiq Payme token → shifrlangan satr (DB'ga yoziladigan)."""
    return _fernet().encrypt(plain_token.encode()).decode()


def decrypt_token(enc_token: str) -> str:
    """Shifrlangan satr → ochiq Payme token (undirish paytida ishlatiladi)."""
    return _fernet().decrypt(enc_token.encode()).decode()


# ── Xato turi ────────────────────────────────────────────────────────

class PaymeSubscribeError(Exception):
    """Payme Subscribe API xatosi (JSON-RPC error yoki tarmoq xatosi)."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


# ── Credential / endpoint ────────────────────────────────────────────

def _creds() -> tuple[str, str, str]:
    """platform_settings'dan (merchant_id, key, base_url) qaytaradi.

    Sozlanmagan bo'lsa aniq xato beramiz.
    """
    merchant_id = (platform.get("payme_subscribe_merchant_id") or "").strip()
    key = (platform.get("payme_subscribe_key") or "").strip()
    if not merchant_id or not key:
        raise PaymeSubscribeError(
            -32504, "Payme Subscribe kassasi sozlanmagan (super-admin → platforma sozlamalari)"
        )
    base_url = _TEST_URL if platform.get("payme_subscribe_test_mode", True) else _PROD_URL
    return merchant_id, key, base_url


def is_configured() -> bool:
    """Subscribe kassasi to'liq sozlanganmi (UI uchun)."""
    return bool(
        (platform.get("payme_subscribe_merchant_id") or "").strip()
        and (platform.get("payme_subscribe_key") or "").strip()
    )


# ── JSON-RPC chaqiruv ────────────────────────────────────────────────

def _redact(params: dict) -> dict:
    """Logga yozishdan oldin maxfiy maydonlarni yashirish (karta raqami, token, kod)."""
    safe = dict(params or {})
    if "card" in safe and isinstance(safe["card"], dict):
        c = dict(safe["card"])
        if "number" in c:
            num = str(c["number"])
            c["number"] = "••••" + num[-4:] if len(num) > 4 else "••••"
        safe["card"] = c
    for k in ("token", "code"):
        if k in safe:
            safe[k] = "***"
    return safe


async def _rpc(method: str, params: dict, *, server_auth: bool) -> dict:
    """Payme Subscribe JSON-RPC chaqiruvi.

    server_auth=False → X-Auth: merchant_id        (cards.create/get_verify_code/verify)
    server_auth=True  → X-Auth: merchant_id:key    (receipts.*, cards.check/remove)
    """
    merchant_id, key, base_url = _creds()
    x_auth = f"{merchant_id}:{key}" if server_auth else merchant_id
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    log.info("Payme Subscribe → %s params=%s", method, _redact(params))
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                base_url,
                json=body,
                headers={"X-Auth": x_auth, "Content-Type": "application/json"},
            )
    except httpx.HTTPError as e:
        raise PaymeSubscribeError(-32400, f"Tarmoq xatosi: {e}") from e

    try:
        data = resp.json()
    except Exception as e:
        raise PaymeSubscribeError(-32400, f"Noto'g'ri javob (JSON emas): {resp.status_code}") from e

    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message")
        if isinstance(msg, dict):  # ko'p tilli xabar
            msg = msg.get("uz") or msg.get("ru") or msg.get("en") or str(msg)
        raise PaymeSubscribeError(int(err.get("code", -1)), str(msg))

    return (data or {}).get("result", {}) if isinstance(data, dict) else {}


# ── Cards (karta bog'lash) ───────────────────────────────────────────

async def cards_create(card_number: str, expire: str, save: bool = True) -> dict:
    """Karta tokenini yaratish. save=True → token keyingi undirishlar uchun saqlanadi.

    expire format: "MMYY" (masalan "0399"). Qaytaradi: {token, recurrent, verify}.
    Token hali TASDIQLANMAGAN — cards.verify dan keyin ishlatish mumkin.
    """
    result = await _rpc(
        "cards.create",
        {"card": {"number": card_number, "expire": expire}, "save": save},
        server_auth=False,
    )
    return result.get("card", {})


async def cards_get_verify_code(token: str) -> dict:
    """Karta egasiga SMS tasdiqlash kodi yuborish. Qaytaradi: {sent, phone, wait}."""
    return await _rpc("cards.get_verify_code", {"token": token}, server_auth=False)


async def cards_verify(token: str, code: str) -> dict:
    """SMS kod bilan tokenni tasdiqlash. Qaytaradi: {card:{token, verify:true, ...}}."""
    result = await _rpc("cards.verify", {"token": token, "code": code}, server_auth=False)
    return result.get("card", {})


async def cards_check(token: str) -> dict:
    """Token holatini tekshirish (server tomoni). Qaytaradi: {card:{verify, ...}}."""
    result = await _rpc("cards.check", {"token": token}, server_auth=True)
    return result.get("card", {})


async def cards_remove(token: str) -> dict:
    """Tokenni Payme tomonida o'chirish. Qaytaradi: {success: true}."""
    return await _rpc("cards.remove", {"token": token}, server_auth=True)


# ── Receipts (undirish) ──────────────────────────────────────────────

async def receipts_create(amount_tiyin: int, account: dict, detail: Optional[dict] = None) -> dict:
    """Chek (invoice) yaratish. amount — tiyin'da. Qaytaradi: {receipt:{_id, ...}}."""
    params: dict[str, Any] = {"amount": int(amount_tiyin), "account": account}
    if detail:
        params["detail"] = detail
    result = await _rpc("receipts.create", params, server_auth=True)
    return result.get("receipt", {})


async def receipts_pay(receipt_id: str, token: str) -> dict:
    """Chekni saqlangan karta tokeni bilan to'lash (server-to-server, sinxron).

    Qaytaradi: {receipt:{_id, state, ...}}. state==4 → muvaffaqiyatli to'langan.
    """
    result = await _rpc("receipts.pay", {"id": receipt_id, "token": token}, server_auth=True)
    return result.get("receipt", {})


async def receipts_check(receipt_id: str) -> dict:
    """Chek holatini tekshirish — rekonsiliatsiya uchun.

    receipts.pay javobi tarmoq xatosi tufayli yo'qolsa (karta yechilgan bo'lishi
    mumkin), keyingi undirishdan OLDIN shu chek holatini tekshiramiz — aks holda
    ikki marta yechib qo'yamiz. Qaytaradi: {_id, state, ...}; state==4 → to'langan.
    """
    result = await _rpc("receipts.check", {"id": receipt_id}, server_auth=True)
    return result.get("receipt", result if isinstance(result, dict) else {})
