"""JWT auth servisi — `SECRET_KEY:rid` statik tokenni almashtirish uchun.

Token strukturasi:
    Header:  {"alg": "HS256", "typ": "JWT"}
    Payload: {
        "sub": "rid:42",       # subject — restaurant id (yoki "super:username")
        "rid": 42,             # restaurant_id (super uchun null)
        "is_super": false,
        "type": "access",      # 'access' | 'refresh'
        "iat": 1234567890,
        "exp": 1234571490,     # access: +1 soat, refresh: +7 kun
        "jti": "uuid"          # token ID (revoke uchun keyinroq ishlatish mumkin)
    }

Backward compat:
    - Eski `SECRET_KEY:rid` token'lari `_parse_legacy_token()` orqali tekshiriladi
    - Login muvaffaqiyatli bo'lsa yangi JWT chiqariladi, eski token'lar 403'gacha tan olinadi

Eslatma: ushbu servis `verify_token()` qaytaradi `TokenContext` — `auth_deps.py`
uni `AuthContext` ga o'tkazadi.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Optional

import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

from api.config import settings


# ── TTL ──────────────────────────────────────────────────────────────────
ACCESS_TOKEN_TTL_SECONDS = 60 * 60          # 1 soat
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 kun
SUPER_ACCESS_TTL_SECONDS = 60 * 60          # 1 soat (audit'ga yozilgani uchun qisqaroq)
# Bot uzoq ishlaydigan jarayon, qayta login qilmaydi — uning scoped JWT'si uzoq TTL.
# (Eski `SECRET_KEY:rid` o'rniga — endi master kalit emas, faqat o'sha restoran huquqi.)
BOT_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30    # 30 kun

JWT_ALGO = "HS256"
JWT_ISSUER = "muhsina-saas"


@dataclass
class TokenContext:
    """JWT payload'dan parsed kontekst."""
    is_super: bool
    restaurant_id: Optional[int]   # super uchun None
    username: Optional[str]        # super uchun u yoki restaurant admin uchun
    token_type: str                # 'access' | 'refresh'
    jti: str                       # unique ID (revocation uchun)
    expires_at: int                # unix epoch


# ── Token chiqarish ──────────────────────────────────────────────────────

def _make_token(payload: dict, ttl_seconds: int) -> str:
    """Asosiy token build helper'i."""
    now = int(time.time())
    full = {
        **payload,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(full, settings.SECRET_KEY, algorithm=JWT_ALGO)


def make_access_token(
    *,
    restaurant_id: Optional[int],
    is_super: bool = False,
    username: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
) -> str:
    """Restaurant admin yoki super-admin uchun access token.

    ttl_seconds berilsa — standart TTL o'rniga ishlatiladi (masalan bot uchun uzoq).
    """
    if is_super:
        sub = f"super:{username or 'admin'}"
        ttl = ttl_seconds or SUPER_ACCESS_TTL_SECONDS
    else:
        if restaurant_id is None:
            raise ValueError("Restaurant admin uchun restaurant_id kerak")
        sub = f"rid:{restaurant_id}"
        ttl = ttl_seconds or ACCESS_TOKEN_TTL_SECONDS

    return _make_token({
        "sub": sub,
        "rid": restaurant_id,
        "is_super": is_super,
        "username": username,
        "type": "access",
    }, ttl)


def make_refresh_token(
    *,
    restaurant_id: Optional[int],
    is_super: bool = False,
    username: Optional[str] = None,
) -> str:
    """Long-lived refresh token. /auth/refresh endpoint'iga jo'natiladi."""
    sub = f"super:{username or 'admin'}" if is_super else f"rid:{restaurant_id}"
    return _make_token({
        "sub": sub,
        "rid": restaurant_id,
        "is_super": is_super,
        "username": username,
        "type": "refresh",
    }, REFRESH_TOKEN_TTL_SECONDS)


def make_token_pair(
    *,
    restaurant_id: Optional[int],
    is_super: bool = False,
    username: Optional[str] = None,
) -> dict:
    """Login javobi uchun {access, refresh, token_type, expires_in}."""
    return {
        "access_token": make_access_token(
            restaurant_id=restaurant_id, is_super=is_super, username=username,
        ),
        "refresh_token": make_refresh_token(
            restaurant_id=restaurant_id, is_super=is_super, username=username,
        ),
        "token_type": "Bearer",
        "expires_in": SUPER_ACCESS_TTL_SECONDS if is_super else ACCESS_TOKEN_TTL_SECONDS,
    }


# ── Token tekshiruv ──────────────────────────────────────────────────────

def verify_token(raw: str, *, expected_type: str = "access") -> Optional[TokenContext]:
    """Tokenni tekshiradi va `TokenContext` qaytaradi.

    None qaytarilsa — yaroqsiz, eskirgan, yoki noto'g'ri tip.

    Args:
        raw: "Bearer xxx" yoki "xxx" (oldindan tozalanmagan ham bo'lishi mumkin)
        expected_type: 'access' (default) yoki 'refresh'
    """
    if not raw:
        return None
    token = raw.replace("Bearer ", "").strip()
    if not token:
        return None

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[JWT_ALGO],
            issuer=JWT_ISSUER,
        )
    except ExpiredSignatureError:
        return None
    except InvalidTokenError:
        return None
    except Exception:
        return None

    if payload.get("type") != expected_type:
        return None

    return TokenContext(
        is_super=bool(payload.get("is_super")),
        restaurant_id=payload.get("rid"),
        username=payload.get("username"),
        token_type=payload.get("type"),
        jti=payload.get("jti", ""),
        expires_at=int(payload.get("exp", 0)),
    )


def refresh_access_token(refresh_token_raw: str) -> Optional[dict]:
    """Refresh token orqali yangi access token (token rotation YO'Q hozircha).

    Refresh token muddatigacha har gal yangi access olishi mumkin.
    Production'da `jti`'ni revocation list bilan tekshirish kerak.
    """
    ctx = verify_token(refresh_token_raw, expected_type="refresh")
    if not ctx:
        return None
    new_access = make_access_token(
        restaurant_id=ctx.restaurant_id,
        is_super=ctx.is_super,
        username=ctx.username,
    )
    ttl = SUPER_ACCESS_TTL_SECONDS if ctx.is_super else ACCESS_TOKEN_TTL_SECONDS
    return {
        "access_token": new_access,
        "token_type": "Bearer",
        "expires_in": ttl,
    }


# ── Backward-compat: eski `SECRET_KEY:rid` formati ──────────────────────

def parse_legacy_token(raw: str) -> Optional[TokenContext]:
    """[O'CHIRILGAN — xavfsizlik] Eski statik `SECRET_KEY` / `SECRET_KEY:rid` tokenlari
    endi QABUL QILINMAYDI. Ular master kalitni oshkor qilardi (auditda Critical C1).
    Faqat JWT va super-HMAC tokenlar ishlatiladi.
    """
    return None


def verify_any_token(raw: str) -> Optional[TokenContext]:
    """Yangi JWT yoki legacy token'ni tan olish — migration davrida foydalanish."""
    ctx = verify_token(raw, expected_type="access")
    if ctx:
        return ctx
    # Eski super HMAC token (SUPER_TOKEN_TTL_SECONDS) — `auth.py`'dan ko'chirib olinmagan
    # — uni alohida `verify_super_token` chaqiradi.
    return parse_legacy_token(raw)
