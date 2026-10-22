"""SMS yuborish xizmati — Eskiz.uz (O'zbekiston).

Eskiz API:
  - Auth:  POST https://notify.eskiz.uz/api/auth/login  (email, password) -> {data:{token}}
  - Send:  POST https://notify.eskiz.uz/api/message/sms/send  (mobile_phone, message, from)
           Authorization: Bearer <token>

Token ~30 kun yashaydi; 401 bo'lsa qayta auth qilamiz. Kalitlar bo'lmasa — MOCK
rejim (faqat logga yozadi, SMS yubormaydi) — lokal/test uchun.

Konfiguratsiya (.env):
  ESKIZ_EMAIL, ESKIZ_PASSWORD, ESKIZ_FROM (ixtiyoriy, default "4546" test-sender).
"""
from __future__ import annotations

import os
import logging

import httpx

log = logging.getLogger("sms")

ESKIZ_BASE = "https://notify.eskiz.uz/api"
_token_cache: dict[str, str] = {}   # {"token": "..."}


def _creds() -> tuple[str, str, str]:
    return (
        (os.getenv("ESKIZ_EMAIL") or "").strip(),
        (os.getenv("ESKIZ_PASSWORD") or "").strip(),
        (os.getenv("ESKIZ_FROM") or "4546").strip(),
    )


def is_configured() -> bool:
    email, password, _ = _creds()
    return bool(email and password)


def _normalize_phone(phone: str) -> str:
    """+998 90 123 45 67 -> 998901234567 (faqat raqamlar)."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    # 9 xonali bo'lsa (90...) — 998 qo'shamiz
    if len(digits) == 9:
        digits = "998" + digits
    return digits


async def _login() -> str | None:
    email, password, _ = _creds()
    if not (email and password):
        return None
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.post(
                f"{ESKIZ_BASE}/auth/login",
                data={"email": email, "password": password},
            )
            r.raise_for_status()
            token = (r.json().get("data") or {}).get("token")
            if token:
                _token_cache["token"] = token
                return token
    except Exception as e:
        log.warning("Eskiz login xato: %s", e)
    return None


async def send_sms(phone: str, message: str) -> dict:
    """Bitta SMS yuborish. Qaytaradi: {"ok": bool, "mock"?: bool, "error"?: str}."""
    mobile = _normalize_phone(phone)
    if not mobile:
        return {"ok": False, "error": "bad_phone"}

    if not is_configured():
        log.info("[SMS MOCK] -> %s : %s", mobile, message)
        return {"ok": True, "mock": True}

    _, _, sender = _creds()

    async def _do(token: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=12.0) as client:
            return await client.post(
                f"{ESKIZ_BASE}/message/sms/send",
                headers={"Authorization": f"Bearer {token}"},
                data={"mobile_phone": mobile, "message": message, "from": sender},
            )

    token = _token_cache.get("token") or await _login()
    if not token:
        return {"ok": False, "error": "auth_failed"}
    try:
        r = await _do(token)
        if r.status_code == 401:  # token eskirgan — qayta auth
            token = await _login()
            if not token:
                return {"ok": False, "error": "auth_failed"}
            r = await _do(token)
        if r.status_code in (200, 201):
            return {"ok": True}
        log.warning("Eskiz SMS xato %s: %s", r.status_code, r.text[:200])
        return {"ok": False, "error": f"http_{r.status_code}"}
    except Exception as e:
        log.warning("Eskiz SMS yuborishda xato: %s", e)
        return {"ok": False, "error": "network"}
