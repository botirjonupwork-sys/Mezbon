"""Parol hashing va tekshiruv — bcrypt asosiy, SHA-256 backward-compat.

Yangi parollar bcrypt'da hashlanadi (`hash_password`).
Eski SHA-256 hash'lar `verify_password` orqali tan olinadi va muvaffaqiyatli
login'dan keyin avtomatik bcrypt'ga ko'chiriladi (`needs_rehash`).

Foydalanish:
    from api.services.security import hash_password, verify_password, needs_rehash

    # Yangi parol
    hashed = hash_password(plain)

    # Login paytida
    if verify_password(plain, db_hash):
        if needs_rehash(db_hash):
            user.password_hash = hash_password(plain)  # avtomatik upgrade
            await db.commit()
"""
from __future__ import annotations

import hashlib
import re

from passlib.context import CryptContext


# Birinchi bcrypt sxemasi, qolganlari (sha256_crypt, sha256) — backward compat
# `deprecated="auto"` — eski sxemalar `needs_update()` True qaytaradi
_pwd_context = CryptContext(
    schemes=["bcrypt", "sha256_crypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

# SHA-256 hex string formati (legacy: 64 ta hex belgi)
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def hash_password(plain: str) -> str:
    """Yangi parol uchun bcrypt hash."""
    if not plain:
        raise ValueError("Parol bo'sh bo'lmasligi kerak")
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Plain parolni hash bilan solishtiradi.

    Qo'llab-quvvatlanadi:
    - bcrypt: $2b$... yoki $2a$...
    - sha256_crypt: $5$...
    - Legacy SHA-256 hex (64 belgi) — eski Restaurant.admin_password_hash format
    """
    if not plain or not hashed:
        return False

    # Legacy SHA-256 hex — passlib bilmaydi, qo'lda tekshiramiz
    if _SHA256_HEX_RE.match(hashed):
        calc = hashlib.sha256(plain.encode()).hexdigest()
        # constant-time taqqoslash
        return _const_time_eq(calc, hashed)

    # bcrypt yoki passlib qo'llab-quvvatlaydigan format
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        # Yaroqsiz hash format
        return False


def needs_rehash(hashed: str) -> bool:
    """Hash bcrypt'ga o'tkazilishi kerakmi (legacy SHA-256 yoki eski rounds)?"""
    if not hashed:
        return True
    if _SHA256_HEX_RE.match(hashed):
        return True   # SHA-256 → bcrypt
    try:
        return _pwd_context.needs_update(hashed)
    except Exception:
        return True


def _const_time_eq(a: str, b: str) -> bool:
    """Timing-safe string taqqoslash."""
    if len(a) != len(b):
        return False
    res = 0
    for x, y in zip(a.encode(), b.encode()):
        res |= x ^ y
    return res == 0


def get_bot_secret_candidates() -> list[str]:
    """Bot-server autentifikatsiya uchun ruxsat etilgan secret'lar ro'yxati.

    Production'da BOT_API_SECRET o'rnatilishi tavsiya etiladi (SECRET_KEY'dan ajratish).
    Backward-compat uchun SECRET_KEY ham qabul qilinadi.
    """
    import os
    from api.config import settings
    out = []
    bot_api = (os.getenv("BOT_API_SECRET") or "").strip()
    if bot_api:
        out.append(bot_api)
    if settings.SECRET_KEY:
        out.append(settings.SECRET_KEY)
    return [s for s in out if s]


def is_valid_bot_secret(token: str) -> bool:
    """Header'dagi X-Bot-Secret yaroqlimi?"""
    if not token:
        return False
    for candidate in get_bot_secret_candidates():
        if _const_time_eq(token, candidate):
            return True
    return False
