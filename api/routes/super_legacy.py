"""Eski super_admin frontend bilan moslik uchun /super/* endpointlari.

Yangi panel `/super-admin/*` ostida qurilgan, lekin mavjud `super_admin/`
React loyihasi `/super/*` URL'larni chaqiradi. Bu router shu eski path'larga
ega minimal qopqoqlarni taqdim qiladi:

    GET/POST/PUT/DELETE /super/plans       — tariflar CRUD
    GET/PUT             /super/profile     — super-admin login ma'lumoti
    GET/PUT             /super/platform-settings — global sozlamalar
    GET                 /super/bots/status  + start/stop/restart (stub)

Auth: hammasi `require_superuser` (qisqa muddatli super token).
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.routes.super_admin import _client_ip, _log_action, require_superuser
from api.services import platform
from database.models import Plan


router = APIRouter(prefix="/super", tags=["super-legacy"])


# ── Plans CRUD ───────────────────────────────────────────────────────────

class PlanIn(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    monthly_price: float = 0.0
    commission_percent: float = 0.0
    # Funksional bayroqlar
    has_catering: bool = False
    has_ai_agent: bool = False
    has_yandex: bool = False
    has_multi_branch: bool = False
    # Limitlar
    max_branches_limit: int = 1     # 0 = cheksiz
    order_limit: int = 0            # 0 = cheksiz
    min_prepayment_percent: int = 30
    features: Optional[list[str]] = None
    is_active: bool = True


def _plan_to_dict(p: Plan) -> dict[str, Any]:
    """Plan obyektni eski frontend kutgan shakliga aylantirish."""
    try:
        features = json.loads(p.features) if p.features else []
        if not isinstance(features, list):
            features = []
    except Exception:
        features = []
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "description": p.description,
        "monthly_price": float(p.monthly_price or 0),
        "commission_percent": float(p.commission_percent or 0),
        # Bayroqlar
        "has_catering": bool(p.has_catering),
        "has_ai_agent": bool(p.has_ai_agent),
        "has_yandex": bool(p.has_yandex),
        "has_multi_branch": bool(p.has_multi_branch),
        # Limitlar
        "max_branches_limit": int(p.max_branches_limit or 0),
        "order_limit": int(p.order_limit or 0),
        "min_prepayment_percent": int(p.min_prepayment_percent or 30),
        "features": features,
        "is_active": bool(p.is_active),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("/plans")
async def list_plans(
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(Plan).order_by(Plan.id))).scalars().all()
    return [_plan_to_dict(p) for p in rows]


@router.post("/plans")
async def create_plan(
    body: PlanIn,
    request: Request,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    # slug takrorlanmasligi
    existing = await db.execute(select(Plan).where(Plan.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"slug='{body.slug}' allaqachon mavjud")
    p = Plan(
        name=body.name,
        slug=body.slug,
        description=body.description,
        monthly_price=body.monthly_price,
        commission_percent=body.commission_percent,
        has_catering=body.has_catering,
        has_ai_agent=body.has_ai_agent,
        has_yandex=body.has_yandex,
        has_multi_branch=body.has_multi_branch,
        max_branches_limit=body.max_branches_limit,
        order_limit=body.order_limit,
        min_prepayment_percent=body.min_prepayment_percent,
        features=json.dumps(body.features or [], ensure_ascii=False),
        is_active=body.is_active,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    await _log_action(
        db, actor=actor.get("u", "super"), action="plan.create",
        target_type="plan", target_id=p.id,
        details={"name": p.name, "slug": p.slug}, ip=_client_ip(request),
    )
    return _plan_to_dict(p)


@router.put("/plans/{plan_id}")
async def update_plan(
    plan_id: int,
    body: PlanIn,
    request: Request,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Plan).where(Plan.id == plan_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Tarif topilmadi")
    before = _plan_to_dict(p)
    p.name = body.name
    p.slug = body.slug
    p.description = body.description
    p.monthly_price = body.monthly_price
    p.commission_percent = body.commission_percent
    p.has_catering = body.has_catering
    p.has_ai_agent = body.has_ai_agent
    p.has_yandex = body.has_yandex
    p.has_multi_branch = body.has_multi_branch
    p.max_branches_limit = body.max_branches_limit
    p.order_limit = body.order_limit
    p.min_prepayment_percent = body.min_prepayment_percent
    p.features = json.dumps(body.features or [], ensure_ascii=False)
    p.is_active = body.is_active
    await db.commit()
    await db.refresh(p)
    await _log_action(
        db, actor=actor.get("u", "super"), action="plan.update",
        target_type="plan", target_id=p.id,
        details={"before": before, "after": _plan_to_dict(p)},
        ip=_client_ip(request),
    )
    return _plan_to_dict(p)


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: int,
    request: Request,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Plan).where(Plan.id == plan_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Tarif topilmadi")
    snapshot = _plan_to_dict(p)
    await db.delete(p)
    await db.commit()
    await _log_action(
        db, actor=actor.get("u", "super"), action="plan.delete",
        target_type="plan", target_id=plan_id, details=snapshot,
        ip=_client_ip(request),
    )
    return {"ok": True}


# ── Profile (super-admin login ma'lumoti) ───────────────────────────────

class ProfileUpdate(BaseModel):
    new_username: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


@router.get("/profile")
async def get_profile(actor: dict = Depends(require_superuser)):
    """Joriy super-admin'ning login va meta ma'lumotlari.

    Parol va boshqalar `.env`'da, biz faqat o'qib qaytaramiz.
    """
    return {
        "username": actor.get("u") or settings.SUPER_ADMIN_USERNAME,
        "name": "Super Admin",
        "role": "super_admin",
    }


@router.put("/profile")
async def update_profile(
    body: ProfileUpdate,
    request: Request,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Super-admin'ning login/parol o'zgartirishi.

    DIQQAT: hozirgi versiyada parol/login `.env` faylida saqlanadi va
    static. Real production'da bularni Vault yoki alohida tablega
    o'tkazish kerak. Bu endpoint hozircha 501 qaytaradi (manual edit).
    """
    raise HTTPException(
        501,
        "Profil o'zgartirish hozircha .env orqali bajariladi. "
        "Server tomonida SUPER_ADMIN_USERNAME va SUPER_ADMIN_PASSWORD'ni o'zgartiring.",
    )


# ── Platform settings (maintenance + brending) ──────────────────────────

class PlatformSettingsUpdate(BaseModel):
    platform_name: Optional[str] = None
    platform_url: Optional[str] = None
    support_phone: Optional[str] = None
    support_email: Optional[str] = None
    default_plan: Optional[str] = None
    default_min_order: Optional[float] = None
    default_delivery_base_fee: Optional[float] = None
    default_delivery_per_km: Optional[float] = None
    default_work_from: Optional[str] = None
    default_work_until: Optional[str] = None
    # AI Call Operator — multi-provider
    ai_llm_provider: Optional[str] = None    # 'openai' | 'groq' | 'anthropic' | 'gemini'
    ai_llm_model: Optional[str] = None
    ai_llm_api_keys: Optional[dict] = None   # {provider_name: api_key}
    ai_stt_provider: Optional[str] = None    # 'openai' | 'groq'
    ai_tts_provider: Optional[str] = None    # 'openai' | 'none'
    ai_voice_gateway: Optional[str] = None
    # Payme Subscribe — restoran obunalarini avtomatik undirish (platforma kassasi)
    payme_subscribe_merchant_id: Optional[str] = None
    payme_subscribe_key: Optional[str] = None       # maskalanadi (GET'da qaytmaydi)
    payme_subscribe_test_mode: Optional[bool] = None


@router.get("/platform-settings")
async def get_platform_settings(actor: dict = Depends(require_superuser)):
    """Platform-level sozlamalar (brending + standart restoran qiymatlari + AI provayder)."""
    from api.services.llm import list_providers

    data = platform.get_all()

    # Multi-provider API keys — har biri uchun mask
    keys = data.get("ai_llm_api_keys") or {}
    # Backward compat: eski ai_llm_api_key (OpenAI uchun) ham qabul qilamiz
    if not keys and data.get("ai_llm_api_key"):
        keys = {"openai": data["ai_llm_api_key"]}

    api_keys_status = {}
    for pname in ("openai", "groq", "anthropic", "gemini", "aisha"):
        k = (keys.get(pname) or "").strip()
        api_keys_status[pname] = {
            "set": bool(k),
            "masked": (f"…{k[-4:]}" if len(k) >= 4 else ""),
        }

    return {
        "platform_name": data.get("platform_name", "SaaS Buyurtma Platformasi"),
        "platform_url": data.get("platform_url", ""),
        "support_phone": data.get("support_phone", ""),
        "support_email": data.get("support_email", ""),
        "default_plan": data.get("default_plan", "free"),
        "default_min_order": data.get("default_min_order", 30000),
        "default_delivery_base_fee": data.get("default_delivery_base_fee", 10000),
        "default_delivery_per_km": data.get("default_delivery_per_km", 3000),
        "default_work_from": data.get("default_work_from", "09:00"),
        "default_work_until": data.get("default_work_until", "22:00"),
        # Maintenance
        "maintenance_mode": data.get("maintenance_mode", False),
        "maintenance_message": data.get("maintenance_message", ""),
        # AI Call Operator — multi-provider
        "ai_llm_provider": data.get("ai_llm_provider", "openai"),
        "ai_llm_model": data.get("ai_llm_model", "gpt-4o-mini"),
        "ai_llm_api_keys_status": api_keys_status,    # {provider: {set, masked}}
        "ai_stt_provider": data.get("ai_stt_provider", "openai"),
        "ai_tts_provider": data.get("ai_tts_provider", "openai"),
        "ai_voice_gateway": data.get("ai_voice_gateway", "telegram"),
        # Provider katalogini ham qaytaramiz — UI dinamik tarzda model list yangilashi uchun
        "ai_providers": list_providers(),
        # Payme Subscribe (obuna avtopay) — kalit maskalanadi
        "payme_subscribe_merchant_id": data.get("payme_subscribe_merchant_id", ""),
        "payme_subscribe_test_mode": data.get("payme_subscribe_test_mode", True),
        "payme_subscribe_configured": bool(
            (data.get("payme_subscribe_merchant_id") or "").strip()
            and (data.get("payme_subscribe_key") or "").strip()
        ),
        "payme_subscribe_key_status": {
            "set": bool((data.get("payme_subscribe_key") or "").strip()),
            "masked": (lambda k: f"…{k[-4:]}" if len(k) >= 4 else "")(
                (data.get("payme_subscribe_key") or "").strip()
            ),
        },
    }


@router.put("/platform-settings")
async def update_platform_settings(
    body: PlatformSettingsUpdate,
    request: Request,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not updates:
        return platform.get_all()

    # ai_llm_api_keys — partial merge (faqat o'zgargan kalitlarni almashtirish)
    if "ai_llm_api_keys" in updates:
        incoming = updates.pop("ai_llm_api_keys") or {}
        current = platform.get("ai_llm_api_keys") or {}
        if not isinstance(current, dict):
            current = {}
        # Backward compat: eski ai_llm_api_key (faqat OpenAI uchun)
        if not current and platform.get("ai_llm_api_key"):
            current = {"openai": platform.get("ai_llm_api_key")}
        merged = dict(current)
        for pname, val in incoming.items():
            if val is None:
                continue
            if val == "":
                # Bo'sh string → kalitni o'chirish
                merged.pop(pname, None)
            else:
                merged[pname] = val
        updates["ai_llm_api_keys"] = merged

    # Payme Subscribe kaliti — bo'sh yoki maskalangan ("…"/"•") qiymat kelsa eski qiymat saqlanadi
    if "payme_subscribe_key" in updates:
        val = (updates.get("payme_subscribe_key") or "").strip()
        if not val or "…" in val or "•" in val:
            updates.pop("payme_subscribe_key", None)

    before = platform.get_all()
    after = platform.set_many(updates)
    # API kalitlarni audit logga plaintext yozmaymiz
    log_updates = dict(updates)
    if "payme_subscribe_key" in log_updates:
        log_updates["payme_subscribe_key"] = "(set)"
    if "ai_llm_api_keys" in log_updates:
        log_updates["ai_llm_api_keys"] = {
            k: (f"…{v[-4:]}" if v and len(v) >= 4 else "(set)") if v else "(cleared)"
            for k, v in (log_updates["ai_llm_api_keys"] or {}).items()
        }
    await _log_action(
        db, actor=actor.get("u", "super"), action="platform.update",
        target_type="platform", target_id=None,
        details={"changed": log_updates},
        ip=_client_ip(request),
    )
    # Response'da ham plaintext kalitni qaytarmaymiz — GET endpoint formatida qaytaramiz
    return await get_platform_settings(actor=actor)


# ── Bot boshqaruvi (stub — manual systemd) ──────────────────────────────

@router.get("/bots/status")
async def bots_status(
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Restoranlar bo'yicha bot tokenlari va Telegram'da real holati.

    Bo'lib chiqadi:
      - Restaurant.bot_token va courier_bot_token ko'rsatilgan ro'yxat
      - Har token uchun `getMe()` chaqirib, bot real ishlayotganini tekshiradi
    """
    import httpx
    from sqlalchemy import select
    from database.models import Restaurant

    rests = (await db.execute(select(Restaurant).order_by(Restaurant.id))).scalars().all()

    async def _check_bot(token: Optional[str]) -> dict:
        if not token:
            return {"configured": False, "online": False}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            if r.status_code == 200:
                data = r.json().get("result", {})
                return {
                    "configured": True, "online": True,
                    "username": data.get("username"),
                    "first_name": data.get("first_name"),
                    "id": data.get("id"),
                }
            return {"configured": True, "online": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"configured": True, "online": False, "error": str(e)[:80]}

    items = []
    for rest in rests:
        cust = await _check_bot(rest.bot_token)
        cour = await _check_bot(rest.courier_bot_token)
        items.append({
            "restaurant_id": rest.id,
            "restaurant_name": rest.name,
            "status": rest.status,
            "subscription_status": rest.subscription_status,
            "customer_bot": cust,
            "courier_bot": cour,
        })

    summary = {
        "total_restaurants": len(items),
        "customer_bots_online": sum(1 for i in items if i["customer_bot"].get("online")),
        "courier_bots_online": sum(1 for i in items if i["courier_bot"].get("online")),
        "customer_bots_configured": sum(1 for i in items if i["customer_bot"].get("configured")),
        "courier_bots_configured": sum(1 for i in items if i["courier_bot"].get("configured")),
    }

    return {"ok": True, "summary": summary, "items": items}


@router.post("/bots/start")
async def bots_start(actor: dict = Depends(require_superuser)):
    raise HTTPException(
        501,
        "Bot ishga tushirish: ssh root@server && systemctl start restaurant-bots",
    )


@router.post("/bots/stop")
async def bots_stop(actor: dict = Depends(require_superuser)):
    raise HTTPException(
        501,
        "Bot to'xtatish: ssh root@server && systemctl stop restaurant-bots",
    )


@router.post("/bots/restart")
async def bots_restart(
    request: Request,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """BARCHA restoran botlarini qayta ishga tushirish (bot_reload_at signali).

    systemctl/docker'ga bog'liq emas — bot menejeri (bot/manager.py) bu signalni
    ~10 sekund ichida ko'rib, har bir token bor restoran botini restart qiladi.
    """
    from datetime import datetime
    from sqlalchemy import or_
    from database.models import Restaurant

    now = datetime.utcnow()
    rests = (await db.execute(
        select(Restaurant).where(
            or_(Restaurant.bot_token.isnot(None), Restaurant.courier_bot_token.isnot(None))
        )
    )).scalars().all()
    n = 0
    for r in rests:
        if (r.bot_token or "").strip() or (r.courier_bot_token or "").strip():
            r.bot_reload_at = now
            n += 1
    await db.commit()
    await _log_action(
        db, actor=actor.get("u", "super"), action="bots.restart_all",
        target_type="bots", target_id=None, details={"count": n}, ip=_client_ip(request),
    )
    return {"ok": True, "count": n, "message": f"{n} ta restoran boti restart signali yuborildi (~10s)"}


@router.post("/bots/{restaurant_id}/restart")
async def bot_restart_one(
    restaurant_id: int,
    request: Request,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """BITTA restoran botini qayta ishga tushirish (bot_reload_at signali)."""
    from datetime import datetime
    from database.models import Restaurant

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")
    if not ((rest.bot_token or "").strip() or (rest.courier_bot_token or "").strip()):
        raise HTTPException(400, "Bu restoranda bot tokeni yo'q")
    rest.bot_reload_at = datetime.utcnow()
    await db.commit()
    await _log_action(
        db, actor=actor.get("u", "super"), action="bots.restart_one",
        target_type="restaurant", target_id=rest.id, details={"name": rest.name},
        ip=_client_ip(request),
    )
    return {"ok": True, "message": f"{rest.name} boti restart signali yuborildi (~10s)"}
