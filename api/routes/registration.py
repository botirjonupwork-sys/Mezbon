"""Restoran ro'yxatdan o'tish endpointi.

Bu endpoint `auth.py` ga o'xshab login emas — yangi tenant (restoran) yaratadi:

    POST /admin/register
    Body: {inn, restaurant_name, admin_username, admin_password, phone?, address?}

Xavfsizlik qatlamlari (faza 1):
1. **Rate limit** — 3/min IP bo'yicha (brute-force va spam'dan)
2. **INN format validatsiyasi** — 9 raqam, blacklist, hech bir bir xil raqam
3. **INN unique** — bir INN bilan ikki marta ro'yxatdan o'tib bo'lmaydi
4. **Username unique** — bir restoran ichida unique username
5. **Parol hashing** — bcrypt (sha256 emas)
6. **Audit log** — har register attempt yoziladi (success/failed)
7. **JWT** — muvaffaqiyatli register'da access + refresh token qaytariladi
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.audit import client_ip, log_security
from api.services.auth_service import make_token_pair
from api.services.inn_validator import (
    InvalidINNError, validate_inn_format,
)
from api.services.security import hash_password
from database.models import Restaurant


router = APIRouter(prefix="/admin", tags=["registration"])

# Brute-force va spam'dan himoya — 3 ta urinish/min IP'dan
_register_limiter = Limiter(key_func=get_remote_address)


# ── Schemas ──────────────────────────────────────────────────────────────

# Slug formati — kichik harf, raqam va defis (URL-safe)
_SLUG_RE = re.compile(r"^[a-z0-9\-]{3,40}$")
# Username formati — alfanumerik + underscore, 3..32 belgi
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class RegisterIn(BaseModel):
    """Ro'yxatdan o'tish payload'i.

    Pydantic field_validator bilan barcha tekshiruvlar Schema darajasida —
    endpoint'ga noto'g'ri ma'lumot kelishi uchun chiqib ham ko'rmaydi.
    """
    # INN — 9 xonali raqam (validator avtomatik tozalaydi)
    inn: str = Field(..., min_length=9, max_length=15)
    # Restoran nomi — 3..120 belgi
    restaurant_name: str = Field(..., min_length=3, max_length=120)
    # Slug — URL'ga moslashtirilgan unique kalit
    slug: Optional[str] = Field(None, min_length=3, max_length=40)
    # Admin login va parol
    admin_username: str = Field(..., min_length=3, max_length=32)
    admin_password: str = Field(..., min_length=8, max_length=128)
    # Ixtiyoriy
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=255)

    @field_validator("inn")
    @classmethod
    def _check_inn(cls, v: str) -> str:
        try:
            return validate_inn_format(v)
        except InvalidINNError as e:
            raise ValueError(str(e))

    @field_validator("admin_username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError(
                "Username faqat lotin harfi, raqam va '_' (3..32 belgi)"
            )
        return v.lower()

    @field_validator("admin_password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Parol kamida 8 belgidan iborat bo'lishi kerak")
        # Oson parollarni rad etish (eng tez-tez ishlatiladiganlar)
        weak = {"password", "12345678", "qwerty12", "admin123", "11111111"}
        if v.lower() in weak:
            raise ValueError("Bu parol juda oddiy — boshqa tanlang")
        return v

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        digits = re.sub(r"\D", "", v)
        if not digits.startswith("998") or len(digits) != 12:
            raise ValueError("Telefon +998XXXXXXXXX formatida bo'lishi kerak")
        return f"+{digits}"

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError("Slug faqat kichik harf, raqam va defis (3..40 belgi)")
        return v


class RegisterOut(BaseModel):
    restaurant_id: int
    inn: str
    name: str
    slug: str
    is_verified: bool
    subscription_status: str
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


# ── Helper: slug avtomatik generatsiya ──────────────────────────────────

def _generate_slug(name: str) -> str:
    """Restoran nomidan slug yaratish (URL-safe)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "restaurant")[:40]


async def _ensure_unique_slug(slug: str, db: AsyncSession) -> str:
    """Slug takrorlanmasligini ta'minlash — kerak bo'lsa raqam qo'shish."""
    base = slug
    n = 1
    while True:
        exists = await db.execute(select(Restaurant.id).where(Restaurant.slug == slug))
        if not exists.scalar_one_or_none():
            return slug
        n += 1
        slug = f"{base}-{n}"
        if n > 100:
            raise HTTPException(409, "Slug yaratib bo'lmadi (juda ko'p urinish)")


# ── Endpoint ────────────────────────────────────────────────────────────

@router.post("/register", response_model=RegisterOut)
@_register_limiter.limit("3/minute")
async def register_restaurant(
    request: Request,
    body: RegisterIn,
    db: AsyncSession = Depends(get_db),
):
    """Yangi restoran (tenant) ro'yxatdan o'tish.

    Multi-tenant izolatsiya: yaratilgan restoran o'z `id` va `inn` bilan
    boshqa restoranlar ma'lumotlariga kira olmaydi. JWT token'da `rid` kodlangan
    va har endpoint `get_restaurant_context` orqali tekshiradi.
    """
    ip = client_ip(request)
    user_agent = request.headers.get("user-agent")

    # ── 1. INN unique tekshiruvi ──────────────────────
    inn_existing = await db.execute(
        select(Restaurant).where(Restaurant.inn == body.inn)
    )
    if inn_existing.scalar_one_or_none():
        await log_security(
            db, action="register.failed", actor_username=body.admin_username,
            ip_address=ip, user_agent=user_agent,
            details={"reason": "inn_taken", "inn": body.inn},
            success=False,
        )
        raise HTTPException(409, {
            "code": "inn_already_registered",
            "message": "Bu INN bilan restoran allaqachon ro'yxatdan o'tgan",
        })

    # ── 2. Slug yaratish va unique qilish ─────────────
    slug = body.slug or _generate_slug(body.restaurant_name)
    slug = await _ensure_unique_slug(slug, db)

    # ── 3. Username unique (global emas, lekin yaxshiroq UX uchun) ────
    # Restaurant.admin_username — har restoranning o'z admini, lekin login
    # paytida butun jadvaldan qidiriladi → unique bo'lishi kerak
    username_existing = await db.execute(
        select(Restaurant).where(Restaurant.admin_username == body.admin_username)
    )
    if username_existing.scalar_one_or_none():
        await log_security(
            db, action="register.failed", actor_username=body.admin_username,
            ip_address=ip, user_agent=user_agent,
            details={"reason": "username_taken"},
            success=False,
        )
        raise HTTPException(409, {
            "code": "username_taken",
            "message": "Bu username allaqachon band — boshqa username tanlang",
        })

    # ── 4. Restoranni yaratish ─────────────────────────
    rest = Restaurant(
        name=body.restaurant_name,
        slug=slug,
        inn=body.inn,
        phone=body.phone,
        address=body.address,
        admin_username=body.admin_username,
        admin_password_hash=hash_password(body.admin_password),
        is_verified=False,         # yangi restoran tekshirilmagan
        subscription_status="active",   # default 30 kun trial
        status="trial",            # admin level — keyinroq active'ga o'tadi
    )
    db.add(rest)
    await db.commit()
    await db.refresh(rest)

    # ── 5. JWT token pair (access + refresh) ──────────
    tokens = make_token_pair(
        restaurant_id=rest.id, is_super=False, username=body.admin_username,
    )

    # ── 6. Audit yozuv (success) ──────────────────────
    await log_security(
        db, action="register",
        restaurant_id=rest.id, actor_username=body.admin_username,
        ip_address=ip, user_agent=user_agent,
        details={
            "inn": body.inn, "name": body.restaurant_name, "slug": slug,
            "phone": body.phone, "rid": rest.id,
        },
        success=True,
    )

    return RegisterOut(
        restaurant_id=rest.id,
        inn=rest.inn,
        name=rest.name,
        slug=rest.slug,
        is_verified=rest.is_verified,
        subscription_status=rest.subscription_status,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_in=tokens["expires_in"],
    )
