"""Authentication dependencies — Admin va Super Admin uchun token tekshirish.

Token formatlari:
- Super Admin: `<SECRET_KEY>` (faqat)
- Restaurant Admin: `<SECRET_KEY>:<restaurant_id>`

Plan feature gating:
- `require_plan_feature("catering")` kabi factory'lar restoranning tarifida
  tegishli funksiya yoqilganligini tekshiradi.
"""
from typing import Optional
from fastapi import Depends, HTTPException, Header, Query
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.config import settings
from api.database import get_db
from database.models import Restaurant, Plan


@dataclass
class AuthContext:
    """Auth natijasi — token orqali aniqlangan kontekst."""
    is_super: bool = False
    restaurant_id: Optional[int] = None  # Super admin uchun None


def _parse_token(raw: str) -> Optional[AuthContext]:
    """Token'ni parse qilish. None qaytarilsa — noto'g'ri token.

    Qo'llab-quvvatlanadi:
    - Yangi qisqa muddatli super token: <payload_b64>.<sig_b64> (HMAC + exp)
    - Legacy super token: bare SECRET_KEY (backward-compat)
    - Restaurant admin: SECRET_KEY:restaurant_id
    """
    if not raw:
        return None
    token = raw.replace("Bearer ", "").strip()
    if not token:
        return None

    # Yangi format — qisqa muddatli super token
    if token.count(".") == 1 and ":" not in token:
        from api.routes.auth import verify_super_token  # circular import'ni oldini olish
        payload = verify_super_token(token)
        if payload:
            return AuthContext(is_super=True, restaurant_id=None)
        # exp tugagan bo'lsa — yaroqsiz
        return None

    # Legacy super: bare SECRET_KEY (backward-compat)
    if token == settings.SECRET_KEY:
        return AuthContext(is_super=True, restaurant_id=None)

    # Restaurant admin: SECRET_KEY:restaurant_id
    if ":" in token:
        secret, rid = token.rsplit(":", 1)
        if secret == settings.SECRET_KEY:
            try:
                return AuthContext(is_super=False, restaurant_id=int(rid))
            except ValueError:
                return None
    return None


async def require_auth(authorization: str = Header(..., alias="Authorization")) -> AuthContext:
    """Har qanday autentifikatsiya qilingan foydalanuvchini tekshiradi.

    Rotate qilgan keyin: invalidate all old tokens. Hozir bu static.
    """
    ctx = _parse_token(authorization)
    if not ctx:
        raise HTTPException(401, "Ruxsat berilmadi — noto'g'ri yoki yo'q token")
    return ctx


async def require_restaurant_admin(
    authorization: str = Header(..., alias="Authorization"),
    restaurant_id: Optional[int] = Query(None),
) -> int:
    """Restaurant admin (yoki super admin) tokenni tekshiradi va restaurant_id qaytaradi.

    Muhim: restaurant_id query param bergan bo'lsa ham, token'dagi restaurant_id asosiy.
    Super admin bo'lsa — query param hurmat qilinadi (ixtiyoriy restaurantlarga kira oladi).
    Restaurant admin bo'lsa — faqat OZ restaurant_id'siga ruxsat.
    """
    ctx = _parse_token(authorization)
    if not ctx:
        raise HTTPException(401, "Ruxsat berilmadi")

    # Super admin har qanday restaurantga kira oladi
    if ctx.is_super:
        if restaurant_id is None:
            # Super admin restaurant tanlamagan bo'lsa — barchasi (None) qaytariladi
            return None  # Endpoint o'zi handle qiladi
        return restaurant_id

    # Restaurant admin — faqat o'ziniki
    if restaurant_id is not None and restaurant_id != ctx.restaurant_id:
        raise HTTPException(403, "Siz boshqa restoran ma'lumotlariga kira olmaysiz")
    return ctx.restaurant_id


async def require_super_admin(
    authorization: str = Header(..., alias="Authorization"),
) -> AuthContext:
    """Faqat super admin tokenini tekshiradi."""
    ctx = _parse_token(authorization)
    if not ctx or not ctx.is_super:
        raise HTTPException(403, "Faqat super admin uchun")
    return ctx


# ── Plan feature gating ──────────────────────────────

# Plan boolean ustun nomlari (database.models.Plan)
_FEATURE_FLAG_MAP = {
    "catering":  "has_catering",
    "ai_agent":  "has_ai_agent",
    "yandex":    "has_yandex",
}


async def get_restaurant_plan(restaurant_id: int, db: AsyncSession) -> Optional[Plan]:
    """Restaurantning joriy tarifi (Plan obyekti). plan_id NULL bo'lsa None qaytadi."""
    result = await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )
    rest = result.scalar_one_or_none()
    if not rest or not rest.plan_id:
        return None
    plan_result = await db.execute(select(Plan).where(Plan.id == rest.plan_id))
    return plan_result.scalar_one_or_none()


def restaurant_has_feature(plan: Optional[Plan], feature_name: str) -> bool:
    """Plan obyektida tegishli flag yoqilganligini sof tarzda tekshirish."""
    if plan is None or not plan.is_active:
        return False
    column_name = _FEATURE_FLAG_MAP.get(feature_name)
    if column_name is None:
        # Noma'lum feature — default rad etamiz
        return False
    return bool(getattr(plan, column_name, False))


def require_plan_feature(feature_name: str):
    """Dependency factory — restoranning tarifi tegishli funksiyani qo'llab-quvvatlashini tekshiradi.

    Foydalanish:
        @router.post("/...", dependencies=[Depends(require_plan_feature("catering"))])
        async def handler(...): ...

    yoki:
        async def handler(restaurant_id: int = Depends(require_plan_feature("catering"))): ...

    Super admin har doim ruxsat oladi (testlash uchun).
    """
    if feature_name not in _FEATURE_FLAG_MAP:
        raise ValueError(f"Noma'lum feature: {feature_name}")

    async def _checker(
        authorization: str = Header(..., alias="Authorization"),
        restaurant_id: Optional[int] = Query(None),
        db: AsyncSession = Depends(get_db),
    ) -> int:
        ctx = _parse_token(authorization)
        if not ctx:
            raise HTTPException(401, "Ruxsat berilmadi")

        # Super admin uchun tekshiruv yo'q
        if ctx.is_super:
            return restaurant_id

        # Restaurant admin — token va query mos kelishi kerak (IDOR guard)
        if restaurant_id is not None and restaurant_id != ctx.restaurant_id:
            raise HTTPException(403, "Siz boshqa restoran ma'lumotlariga kira olmaysiz")
        rid = ctx.restaurant_id

        # Tarif tekshiruvi
        plan = await get_restaurant_plan(rid, db)
        if not restaurant_has_feature(plan, feature_name):
            plan_name = plan.name if plan else "tariff yo'q"
            raise HTTPException(
                403,
                f"Joriy tarif ({plan_name}) ushbu funksiyani ({feature_name}) qo'llab-quvvatlamaydi. "
                f"Tarifni yangilang."
            )
        return rid

    return _checker
