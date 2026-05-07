"""Authentication dependencies — Admin va Super Admin uchun token tekshirish.

Token tartibi (priorit):
1. **JWT** (yangi) — `api/services/auth_service.py` orqali, HS256, `iat/exp/jti`
2. **Super HMAC token** (oldindan, qisqa muddatli) — `api/routes/auth.py:verify_super_token`
3. **Legacy** `SECRET_KEY:rid` yoki bare `SECRET_KEY` — backward-compat

Super-admin IDOR himoyasi:
- `get_restaurant_context()` dep — har endpoint super-admin restoran tanlash kontekstini
  xavfsiz olishi va audit log'ga yozishi uchun
- Restaurant admin token'idagi `rid` query/header bilan farq qilsa — `403`
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from database.models import Plan, Restaurant


@dataclass
class AuthContext:
    """Auth natijasi — token orqali aniqlangan kontekst."""
    is_super: bool = False
    restaurant_id: Optional[int] = None    # Super uchun None
    username: Optional[str] = None
    token_type: str = "legacy"             # 'jwt' | 'super-hmac' | 'legacy'


def _parse_token(raw: str) -> Optional[AuthContext]:
    """Token'ni parse qilish. None qaytarilsa — noto'g'ri token.

    Tartib: JWT → super HMAC → legacy SECRET_KEY[:rid]
    """
    if not raw:
        return None
    token = raw.replace("Bearer ", "").strip()
    if not token:
        return None

    # 1. JWT (yangi format) — uch qism nuqta bilan
    if token.count(".") == 2:
        from api.services.auth_service import verify_token
        ctx = verify_token(token, expected_type="access")
        if ctx:
            return AuthContext(
                is_super=ctx.is_super,
                restaurant_id=ctx.restaurant_id,
                username=ctx.username,
                token_type="jwt",
            )

    # 2. Super HMAC token (qisqa muddatli, oldingi versiyadan) — bitta nuqta
    if token.count(".") == 1 and ":" not in token:
        from api.routes.auth import verify_super_token
        payload = verify_super_token(token)
        if payload:
            return AuthContext(
                is_super=True, restaurant_id=None,
                username=payload.get("u"), token_type="super-hmac",
            )
        return None

    # 3. Legacy super: bare SECRET_KEY
    if token == settings.SECRET_KEY:
        return AuthContext(is_super=True, restaurant_id=None, token_type="legacy")

    # 4. Legacy restaurant: SECRET_KEY:rid
    if ":" in token:
        secret, rid = token.rsplit(":", 1)
        if secret == settings.SECRET_KEY:
            try:
                return AuthContext(
                    is_super=False, restaurant_id=int(rid), token_type="legacy",
                )
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


# ── Super-admin restoran konteksti (IDOR himoyasi + audit) ──────────────

async def get_restaurant_context(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
    restaurant_id: Optional[int] = Query(None),
    x_restaurant_context: Optional[int] = Header(None, alias="X-Restaurant-Context"),
    db: AsyncSession = Depends(get_db),
) -> int:
    """Restoran kontekstini xavfsiz aniqlovchi Dependency.

    Mantiq:
        Restaurant admin:
            - Token'dan `rid` olinadi
            - Agar query/header'da boshqa rid bor bo'lsa → **403** (IDOR)
        Super admin:
            - `X-Restaurant-Context` header (afzal) yoki `restaurant_id` query'dan
            - Tanlangan rid bazada mavjudligini tekshiradi
            - Har super-admin "switch"ni `super_admin_actions` jadvaliga yozadi (audit)

    Qaytaradi: aniqlangan `restaurant_id` (int).
    """
    ctx = _parse_token(authorization)
    if not ctx:
        raise HTTPException(401, "Ruxsat berilmadi")

    # Super-admin: header (afzal) yoki query
    requested_rid = x_restaurant_context if x_restaurant_context is not None else restaurant_id

    if ctx.is_super:
        if requested_rid is None:
            raise HTTPException(
                400,
                "Super-admin uchun X-Restaurant-Context header yoki restaurant_id query majburiy",
            )
        # Mavjudligini tekshirish
        rest = (await db.execute(
            select(Restaurant.id).where(Restaurant.id == int(requested_rid))
        )).scalar_one_or_none()
        if rest is None:
            raise HTTPException(404, f"Restaurant #{requested_rid} topilmadi")

        # Audit log — faqat mutatsiya so'rovlari uchun (GET noise'ni kamaytirish)
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                from database.models import SuperAdminAction
                db.add(SuperAdminAction(
                    actor=ctx.username or "super",
                    action="restaurant.context.access",
                    target_type="restaurant",
                    target_id=int(requested_rid),
                    details=json.dumps({
                        "method": request.method,
                        "path": request.url.path,
                        "via": "header" if x_restaurant_context else "query",
                    }, ensure_ascii=False),
                    ip=_client_ip(request),
                ))
                await db.commit()
            except Exception:
                await db.rollback()  # audit yozish o'tib ketadi

        return int(requested_rid)

    # Restaurant admin — token'dagi rid majburiy, override qilib bo'lmaydi
    if ctx.restaurant_id is None:
        raise HTTPException(401, "Token noto'g'ri (rid yo'q)")

    if requested_rid is not None and int(requested_rid) != ctx.restaurant_id:
        raise HTTPException(
            403,
            "Siz boshqa restoran ma'lumotlariga kira olmaysiz",
        )

    return ctx.restaurant_id


def _client_ip(request: Request) -> Optional[str]:
    """X-Forwarded-For yoki client.host."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Branch IDOR himoyasi ─────────────────────────────────────────────────

async def get_branch_context(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
    branch_id: Optional[int] = Query(None),
    x_branch_context: Optional[int] = Header(None, alias="X-Branch-Context"),
    restaurant_id: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Filial konteksti — restoran kontekstidan keyin filial darajasida IDOR.

    Filial `restaurant_id` ga tegishliligini tekshiradi. Begona filial → 403.

    Qaytaradi: `{"restaurant_id": int, "branch_id": Optional[int]}`.
    Branch berilmagan bo'lsa branch_id None bo'ladi (restoran-darajasidagi operatsiya).
    """
    from database.models import Branch

    requested_bid = x_branch_context if x_branch_context is not None else branch_id

    if requested_bid is None:
        return {"restaurant_id": restaurant_id, "branch_id": None}

    branch = (await db.execute(
        select(Branch).where(Branch.id == int(requested_bid))
    )).scalar_one_or_none()

    if branch is None:
        raise HTTPException(404, f"Branch #{requested_bid} topilmadi")

    if branch.restaurant_id != restaurant_id:
        raise HTTPException(
            403,
            f"Branch #{requested_bid} sizning restoraningizga tegishli emas",
        )

    return {"restaurant_id": restaurant_id, "branch_id": int(requested_bid)}


# ── Plan feature gating ──────────────────────────────

# Plan boolean ustun nomlari (database.models.Plan)
_FEATURE_FLAG_MAP = {
    "catering":     "has_catering",
    "ai_agent":     "has_ai_agent",
    "ai_operator":  "has_ai_agent",      # alias
    "yandex":       "has_yandex",
    "multi_branch": "has_multi_branch",
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
    """Dependency factory — joriy restoran tarifi tegishli funksiyaga ruxsat
    bermasa **402 Payment Required** qaytaradi.

    Faza 3: endi `get_restaurant_context` orqali ishlaydi — super-admin
    `X-Restaurant-Context` header bilan boshqa restoran tarifini ham tekshira oladi.

    Foydalanish:
        @router.get("/catering/...", dependencies=[Depends(require_plan_feature("catering"))])
        async def ...

    Yoki rid bilan:
        async def handler(rid: int = Depends(require_plan_feature("catering"))): ...

    Super admin har doim ruxsat oladi.
    """
    if feature_name not in _FEATURE_FLAG_MAP:
        raise ValueError(f"Noma'lum feature: {feature_name}")

    async def _checker(
        request: Request,
        restaurant_id: int = Depends(get_restaurant_context),
        db: AsyncSession = Depends(get_db),
    ) -> int:
        # Super-admin uchun get_restaurant_context allaqachon validatsiya qildi
        # va restoran ID berib turdi — endi tarif tekshiruvi
        ctx = _parse_token(request.headers.get("Authorization", ""))
        if ctx and ctx.is_super:
            return restaurant_id   # super hech qachon plan'ga bog'liq emas

        plan = await get_restaurant_plan(restaurant_id, db)
        if not restaurant_has_feature(plan, feature_name):
            plan_name = plan.name if plan else "tarif yo'q"
            raise HTTPException(
                402,
                {
                    "code": "plan_feature_required",
                    "feature": feature_name,
                    "current_plan": plan_name,
                    "message": f"Joriy tarif ({plan_name}) {feature_name} funksiyasini "
                               f"qo'llab-quvvatlamaydi. Tarifni yangilang.",
                },
            )
        return restaurant_id

    return _checker
