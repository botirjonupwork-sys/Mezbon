"""Avtomatik obuna to'lovi — restoran kartasini bog'lash (Payme Subscribe).

Oqim:
  1. POST /admin/autopay/card    — karta raqami+muddat → token + SMS kod yuboriladi
  2. POST /admin/autopay/verify  — SMS kod → token tasdiqlanadi va saqlanadi
  3. (har oy) scheduler avtomatik undiradi (api/services/subscription.py)

Xavfsizlik:
  * Karta tokeni faqat server tomonda, SHIFRLANGAN holda (PaymeCard.token_enc) saqlanadi —
    frontendga hech qachon qaytmaydi.
  * Karta raqami saqlanmaydi/loglanmaydi — faqat oxirgi 4 raqam.
  * OTP yuborish DB asosida throttle qilinadi (soatiga 5 marta).
  * Har bir amal audit log'ga yoziladi.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.auth_deps import require_restaurant_admin
from api.services import payme_subscribe as ps
from api.services.audit import log_security, client_ip
from database.models import PaymeCard, Restaurant

router = APIRouter(prefix="/admin/autopay", tags=["autopay"])

_OTP_MAX_PER_HOUR = 5


# ── Schemas ──────────────────────────────────────────

class CardBindRequest(BaseModel):
    card_number: str   # 13–19 raqam
    expire: str        # "MM/YY" yoki "MMYY"


class CardVerifyRequest(BaseModel):
    card_id: int
    code: str


class ToggleRequest(BaseModel):
    enabled: bool


# ── Yordamchi ────────────────────────────────────────

def _normalize_expire(raw: str) -> tuple[str, str]:
    """'03/99' yoki '0399' → (payme_format='0399', display='03/99'). MMYY kutiladi."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) != 4:
        raise HTTPException(400, "Amal muddati formati: MM/YY")
    return digits, f"{digits[:2]}/{digits[2:]}"


async def _active_card(db: AsyncSession, restaurant_id: int) -> Optional[PaymeCard]:
    res = await db.execute(
        select(PaymeCard).where(
            PaymeCard.restaurant_id == restaurant_id,
            PaymeCard.is_active == True,  # noqa: E712
        )
    )
    return res.scalar_one_or_none()


def _require_restaurant(restaurant_id: Optional[int]) -> int:
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak (restoranni tanlang)")
    return restaurant_id


# ── Holat ────────────────────────────────────────────

@router.get("/status")
async def autopay_status(
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Avtomatik to'lov holati (token hech qachon qaytmaydi — faqat oxirgi 4 raqam)."""
    rid = _require_restaurant(restaurant_id)
    rest = (await db.execute(select(Restaurant).where(Restaurant.id == rid))).scalar_one_or_none()
    card = await _active_card(db, rid)
    return {
        "platform_configured": ps.is_configured(),   # super-admin Subscribe kassasini sozlaganmi
        "autopay_enabled": bool(rest and rest.autopay_enabled),
        "has_card": bool(card),
        "card_verified": bool(card and card.verified),
        "card_last4": card.card_last4 if card else None,
        "card_expire": card.card_expire if card else None,
    }


# ── 1) Karta bog'lash (token + SMS) ──────────────────

@router.post("/card")
async def bind_card(
    body: CardBindRequest,
    request: Request,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    rid = _require_restaurant(restaurant_id)
    if not ps.is_configured():
        raise HTTPException(400, "Platforma Payme Subscribe kassasi hali sozlanmagan")

    number = "".join(ch for ch in (body.card_number or "") if ch.isdigit())
    if not (13 <= len(number) <= 19):
        raise HTTPException(400, "Karta raqami noto'g'ri")
    expire_payme, expire_display = _normalize_expire(body.expire)

    # Throttle: oxirgi 1 soatda yaratilgan (tasdiqlanmagan) urinishlar soni
    since = datetime.utcnow() - timedelta(hours=1)
    recent = (await db.execute(
        select(func.count(PaymeCard.id)).where(
            PaymeCard.restaurant_id == rid,
            PaymeCard.created_at >= since,
        )
    )).scalar() or 0
    if recent >= _OTP_MAX_PER_HOUR:
        raise HTTPException(429, "Juda ko'p urinish. Bir oz kutib, qayta urinib ko'ring.")

    try:
        card = await ps.cards_create(number, expire_payme, save=True)
        token = card.get("token")
        if not token:
            raise HTTPException(400, "Payme token qaytarmadi")
        sms = await ps.cards_get_verify_code(token)
    except ps.PaymeSubscribeError as e:
        # Karta raqami logga tushmaydi (ps o'zi redaksiya qiladi)
        raise HTTPException(400, f"Payme xatosi: {e.message}")

    pc = PaymeCard(
        restaurant_id=rid,
        token_enc=ps.encrypt_token(token),
        card_last4=number[-4:],
        card_expire=expire_display,
        verified=False,
        is_active=False,
    )
    db.add(pc)
    await db.commit()
    await db.refresh(pc)

    await log_security(
        db, action="autopay.card.bind", restaurant_id=rid,
        ip_address=client_ip(request),
        details={"card_id": pc.id, "last4": pc.card_last4},
    )
    return {"card_id": pc.id, "phone": sms.get("phone"), "wait": sms.get("wait")}


# ── 2) SMS kod bilan tasdiqlash ──────────────────────

@router.post("/verify")
async def verify_card(
    body: CardVerifyRequest,
    request: Request,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    rid = _require_restaurant(restaurant_id)
    pc = (await db.execute(
        select(PaymeCard).where(
            PaymeCard.id == body.card_id,
            PaymeCard.restaurant_id == rid,
        )
    )).scalar_one_or_none()
    if not pc:
        raise HTTPException(404, "Karta topilmadi")
    if pc.verified:
        return {"verified": True, "card_last4": pc.card_last4}

    try:
        token = ps.decrypt_token(pc.token_enc)
        result = await ps.cards_verify(token, (body.code or "").strip())
    except ps.PaymeSubscribeError as e:
        await log_security(
            db, action="autopay.card.verify", restaurant_id=rid, success=False,
            ip_address=client_ip(request), details={"card_id": pc.id, "error": e.message},
        )
        raise HTTPException(400, f"Tasdiqlash xatosi: {e.message}")

    if not result.get("verify"):
        raise HTTPException(400, "Karta tasdiqlanmadi")

    # Boshqa aktiv kartalarni o'chiramiz (bitta aktiv karta qoidasi)
    others = (await db.execute(
        select(PaymeCard).where(
            PaymeCard.restaurant_id == rid,
            PaymeCard.is_active == True,  # noqa: E712
            PaymeCard.id != pc.id,
        )
    )).scalars().all()
    for o in others:
        o.is_active = False

    pc.verified = True
    pc.is_active = True
    pc.verified_at = datetime.utcnow()

    rest = (await db.execute(select(Restaurant).where(Restaurant.id == rid))).scalar_one_or_none()
    if rest:
        rest.autopay_enabled = True
    await db.commit()

    await log_security(
        db, action="autopay.card.verify", restaurant_id=rid,
        ip_address=client_ip(request), details={"card_id": pc.id, "last4": pc.card_last4},
    )
    return {"verified": True, "card_last4": pc.card_last4}


# ── 3) Kartani o'chirish ─────────────────────────────

@router.delete("/card")
async def remove_card(
    request: Request,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    rid = _require_restaurant(restaurant_id)
    card = await _active_card(db, rid)
    if not card:
        raise HTTPException(404, "Aktiv karta yo'q")

    # Payme tomonida tokenni o'chirishga harakat (xato bo'lsa ham davom etamiz)
    try:
        await ps.cards_remove(ps.decrypt_token(card.token_enc))
    except ps.PaymeSubscribeError as e:
        ps.log.warning("cards.remove xato (davom etamiz): %s", e.message)

    card.is_active = False
    rest = (await db.execute(select(Restaurant).where(Restaurant.id == rid))).scalar_one_or_none()
    if rest:
        rest.autopay_enabled = False
    await db.commit()

    await log_security(
        db, action="autopay.card.remove", restaurant_id=rid,
        ip_address=client_ip(request), details={"card_id": card.id},
    )
    return {"success": True}


# ── Autopay yoqish/o'chirish (kartani saqlab) ────────

@router.post("/toggle")
async def toggle_autopay(
    body: ToggleRequest,
    request: Request,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    rid = _require_restaurant(restaurant_id)
    rest = (await db.execute(select(Restaurant).where(Restaurant.id == rid))).scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")
    if body.enabled:
        card = await _active_card(db, rid)
        if not card or not card.verified:
            raise HTTPException(400, "Avval tasdiqlangan karta bog'lang")
    rest.autopay_enabled = bool(body.enabled)
    await db.commit()
    await log_security(
        db, action="autopay.toggle", restaurant_id=rid,
        ip_address=client_ip(request), details={"enabled": bool(body.enabled)},
    )
    return {"autopay_enabled": rest.autopay_enabled}
