"""AI Call Operator REST endpoints.

Vapi/Retell yoki o'z SIP gateway'imiz transcribed user message'ni shu yerga
yuboradi. Biz LLM (OpenAI function calling) orqali javob va kerakli
action'larni qaytaramiz. Buyurtma tasdiqlansa — ichki `Order` yaratiladi
va catering bo'lsa, mijoz catering kanaliga yo'naltiriladi.
"""
from __future__ import annotations

import base64
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_deps import require_plan_feature
from api.database import get_db
from api.routes.users import get_or_create_phone_user
from api.services import ai_agent, platform, voice as voice_svc
from database.models import (
    DeliveryType, Order, OrderItem, OrderStatus, Restaurant,
)


router = APIRouter(prefix="/ai", tags=["ai"])


# ── Schemas ──────────────────────────────────────────────────────────────

class ProcessCallRequest(BaseModel):
    call_id: str = Field(..., description="Ovozli provider tomonidan beriladigan unikal call ID")
    user_phone: str = Field(..., description="+998XXXXXXXXX formatida")
    message: str = Field(..., description="Foydalanuvchi gapining transcript matni")
    user_name: Optional[str] = None
    end_call: bool = False  # True bo'lsa sessiyani yopamiz


class ProcessCallResponse(BaseModel):
    reply: str
    actions: list[dict]
    cart: list[dict]
    address: Optional[str] = None
    confirmed: bool = False
    transferred: bool = False
    order_id: Optional[int] = None
    is_catering: bool = False


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/process-call", response_model=ProcessCallResponse)
async def process_call(
    body: ProcessCallRequest,
    restaurant_id: int = Depends(require_plan_feature("ai_agent")),
    db: AsyncSession = Depends(get_db),
):
    """Bitta turn — foydalanuvchi reploki uchun AI javob.

    Buyurtma tasdiqlansa (`confirmed=True`) ichki Order yaratamiz va
    `actions` ichida `{"type":"create_order","order_id":N}` qaytaramiz.
    Catering bo'lsa `transferred=True` va `actions=[{"type":"transfer_to_catering"}]`.
    """
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak (super admin uchun ham)")

    rest_res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    restaurant = rest_res.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(404, "Restoran topilmadi")

    if not restaurant.ai_agent_enabled:
        raise HTTPException(403, "AI Operator restoran sozlamalarida o'chirilgan")

    # Sessiya
    sess = ai_agent.get_session(body.call_id, restaurant.id, body.user_phone)

    # AI javobini olish
    result = await ai_agent.process_message(db, restaurant, sess, body.message)

    actions: list[dict] = []
    order_id: Optional[int] = None

    # Ish vaqtidan tashqari / vaqt limiti — sessiyani yopib, end_call signali qaytaramiz
    if result.get("ended_reason") in {"outside_work_hours", "time_limit"}:
        await ai_agent.finalize_session(db, body.call_id, ended_reason=result["ended_reason"])
        actions.append({"type": "end_call", "reason": result["ended_reason"]})
        return ProcessCallResponse(
            reply=result["reply"], actions=actions, cart=result.get("cart", []),
            address=result.get("address"), confirmed=False, transferred=False,
            is_catering=False,
        )

    # Catering yoki transfer
    if result.get("transferred") or (result.get("is_catering") and result.get("confirmed")):
        actions.append({
            "type": "transfer_to_catering",
            "phone": body.user_phone,
            "cart": result.get("cart", []),
            "address": result.get("address"),
        })
        await ai_agent.finalize_session(db, body.call_id, ended_reason="transferred")
        return ProcessCallResponse(
            reply=result["reply"], actions=actions, cart=result.get("cart", []),
            address=result.get("address"), confirmed=False, transferred=True,
            is_catering=bool(result.get("is_catering")),
        )

    # Tasdiqlangan oddiy buyurtma
    if result.get("confirmed") and result.get("cart"):
        try:
            order_id = await _create_ai_order(
                db=db, restaurant_id=restaurant.id,
                phone=body.user_phone, user_name=body.user_name,
                cart=result["cart"], address=result.get("address"),
            )
            actions.append({"type": "create_order", "order_id": order_id})
        except Exception as e:
            actions.append({"type": "error", "message": f"Order yaratishda xato: {e}"})
        await ai_agent.finalize_session(db, body.call_id, ended_reason="confirmed", order_id=order_id)

    if body.end_call:
        await ai_agent.finalize_session(db, body.call_id, ended_reason="user_hangup")

    return ProcessCallResponse(
        reply=result["reply"],
        actions=actions,
        cart=result.get("cart", []),
        address=result.get("address"),
        confirmed=bool(result.get("confirmed")),
        transferred=False,
        order_id=order_id,
        is_catering=bool(result.get("is_catering")),
    )


@router.post("/end-call")
async def end_call(
    call_id: str,
    restaurant_id: int = Depends(require_plan_feature("ai_agent")),
    db: AsyncSession = Depends(get_db),
):
    """Sessiyani yopish (provider call hangup hodisasida) + DB log yozish."""
    await ai_agent.finalize_session(db, call_id, ended_reason="user_hangup")
    return {"ok": True}


# ── Logs & statistics ────────────────────────────────────────────────────

import json as _json
from api.auth_deps import get_restaurant_context


@router.get("/logs")
async def list_call_logs(
    restaurant_id: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """Restoranning AI suhbat tarixi (oxirgi N ta)."""
    from database.models import AICallLog
    rows = (await db.execute(
        select(AICallLog)
        .where(AICallLog.restaurant_id == restaurant_id)
        .order_by(AICallLog.started_at.desc())
        .limit(min(int(limit), 200))
        .offset(int(offset))
    )).scalars().all()

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "call_id": r.call_id,
            "user_phone": r.user_phone,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "duration_seconds": float(r.duration_seconds or 0),
            "message_count": int(r.message_count or 0),
            "tokens_in": int(r.tokens_in or 0),
            "tokens_out": int(r.tokens_out or 0),
            "cost_usd": float(r.cost_usd or 0),
            "ended_reason": r.ended_reason,
            "order_id": r.order_id,
        })
    return {"items": items, "count": len(items)}


@router.get("/logs/{log_id}")
async def get_call_log_detail(
    log_id: int,
    restaurant_id: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
):
    """Bitta suhbat tafsiloti (transcript bilan)."""
    from database.models import AICallLog
    row = (await db.execute(
        select(AICallLog)
        .where(AICallLog.id == log_id, AICallLog.restaurant_id == restaurant_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Suhbat topilmadi")

    transcript = []
    if row.transcript:
        try:
            transcript = _json.loads(row.transcript)
        except Exception:
            transcript = []

    return {
        "id": row.id,
        "call_id": row.call_id,
        "user_phone": row.user_phone,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "duration_seconds": float(row.duration_seconds or 0),
        "message_count": int(row.message_count or 0),
        "tokens_in": int(row.tokens_in or 0),
        "tokens_out": int(row.tokens_out or 0),
        "stt_seconds": float(row.stt_seconds or 0),
        "tts_chars": int(row.tts_chars or 0),
        "cost_usd": float(row.cost_usd or 0),
        "transcript": transcript,
        "order_id": row.order_id,
        "ended_reason": row.ended_reason,
    }


@router.get("/stats")
async def get_call_stats(
    restaurant_id: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
    days: int = 30,
):
    """Oxirgi N kun davomidagi AI suhbatlar bo'yicha statistika."""
    from database.models import AICallLog
    from datetime import datetime, timedelta
    from sqlalchemy import func

    since = datetime.utcnow() - timedelta(days=max(1, min(int(days), 365)))

    q = select(
        func.count(AICallLog.id).label("total"),
        func.coalesce(func.sum(AICallLog.cost_usd), 0).label("total_cost"),
        func.coalesce(func.sum(AICallLog.tokens_in), 0).label("tokens_in"),
        func.coalesce(func.sum(AICallLog.tokens_out), 0).label("tokens_out"),
        func.coalesce(func.sum(AICallLog.duration_seconds), 0).label("duration"),
        func.count(AICallLog.order_id).label("orders_created"),
    ).where(
        AICallLog.restaurant_id == restaurant_id,
        AICallLog.started_at >= since,
    )
    row = (await db.execute(q)).first()

    return {
        "period_days": days,
        "total_calls": int(row.total or 0),
        "total_cost_usd": round(float(row.total_cost or 0), 4),
        "tokens_in": int(row.tokens_in or 0),
        "tokens_out": int(row.tokens_out or 0),
        "total_duration_seconds": float(row.duration or 0),
        "orders_created": int(row.orders_created or 0),
    }


# ── Voice (Telegram audio) endpoint ──────────────────────────────────────

class VoiceTurnResponse(BaseModel):
    transcript: str               # STT natijasi (mijoz nima dedi)
    reply_text: str               # AI javobi (matn)
    reply_audio_b64: Optional[str] = None  # OPUS audio, base64 (Telegram voice uchun)
    actions: list[dict] = []
    cart: list[dict] = []
    address: Optional[str] = None
    confirmed: bool = False
    transferred: bool = False
    order_id: Optional[int] = None
    is_catering: bool = False
    ended_reason: Optional[str] = None


@router.post("/voice-turn", response_model=VoiceTurnResponse)
async def voice_turn(
    call_id: str = Form(..., description="Telegram chat_id'dan olingan unikal sessiya ID"),
    user_phone: str = Form(...),
    user_name: Optional[str] = Form(None),
    audio: UploadFile = File(..., description="OGG/OPUS yoki MP3 audio fayl"),
    end_call: bool = Form(False),
    restaurant_id: int = Depends(require_plan_feature("ai_agent")),
    db: AsyncSession = Depends(get_db),
):
    """Voice turn — audio fayl qabul qiladi va audio javob qaytaradi.

    Pipeline: STT (Whisper) → process_message (AI agent) → TTS (OpenAI).

    Voice gateway = 'telegram' bo'lganda Customer Bot shu endpoint'ga audio yuboradi.
    """
    # Voice gateway 'telegram' yoqilganmi?
    gateway = (platform.get("ai_voice_gateway") or "telegram").lower()
    if gateway != "telegram":
        raise HTTPException(
            400,
            f"Voice gateway '{gateway}' tanlangan — Telegram orqali ovoz ulanmagan",
        )

    rest_res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    restaurant = rest_res.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(404, "Restoran topilmadi")
    if not restaurant.ai_agent_enabled:
        raise HTTPException(403, "AI Operator restoran sozlamalarida o'chirilgan")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "Audio fayl bo'sh")
    if len(audio_bytes) > 20 * 1024 * 1024:   # 20 MB limit (Telegram voice ~ < 1 MB)
        raise HTTPException(413, "Audio fayl juda katta (max 20 MB)")

    # Sessiya (audio uzunligini sessiyaga yozish uchun)
    sess = ai_agent.get_session(call_id, restaurant.id, user_phone)

    # STT — Whisper. Audio davomiyligini taxmin qilamiz: Telegram voice ~ 4-8 KB/sec
    # Aniq davomiylik faqat audio header'idan o'qiladi (bu yerda decode qilmaymiz).
    # Telegram voice obyektining `duration` field'i bot tomonida bilinadi — bot uni alohida
    # endpoint'da yuborishi mumkin (hozircha taxmin qiluvchi heuristic).
    # Whisper xarajati past, taxminiy qiymat yetarli.
    sess.stt_seconds += max(1.0, len(audio_bytes) / 6000.0)  # ~6 KB/sec Telegram Opus
    lang_hint = voice_svc.language_hint(getattr(restaurant, "ai_agent_language", None))

    # Restoran menyusi nomlarini Whisper prompt'iga qo'shamiz —
    # bu Uzbek STT'ni mahsulot nomlarida sezilarli yaxshilaydi.
    try:
        menu_products = await ai_agent.load_menu(db, restaurant.id)
        menu_item_names = [p.name_uz for p in menu_products if p.name_uz]
    except Exception:
        menu_item_names = []

    try:
        transcript = await voice_svc.transcribe(
            audio_bytes,
            filename=audio.filename or "voice.ogg",
            language=lang_hint,
            menu_items=menu_item_names,
        )
    except Exception as e:
        from api.logging_config import log_critical
        log_critical("ai_agent", "STT failed", error=str(e), restaurant_id=restaurant.id)
        raise HTTPException(502, f"STT xatosi: {e}")

    if not transcript:
        return VoiceTurnResponse(
            transcript="", reply_text="Sizni eshitmadim, qaytadan ayting.",
        )

    # AI javob
    result = await ai_agent.process_message(db, restaurant, sess, transcript)

    actions: list[dict] = []
    order_id: Optional[int] = None

    # Vaqt limiti / ish vaqtidan tashqari
    if result.get("ended_reason") in {"outside_work_hours", "time_limit"}:
        await ai_agent.finalize_session(db, call_id, ended_reason=result["ended_reason"])
        actions.append({"type": "end_call", "reason": result["ended_reason"]})
    # Catering yoki transfer
    elif result.get("transferred") or (result.get("is_catering") and result.get("confirmed")):
        actions.append({
            "type": "transfer_to_catering", "phone": user_phone,
            "cart": result.get("cart", []), "address": result.get("address"),
        })
        await ai_agent.finalize_session(db, call_id, ended_reason="transferred")
    # Tasdiqlangan buyurtma
    elif result.get("confirmed") and result.get("cart"):
        order_id = None
        try:
            created = await _create_ai_order(
                db=db, restaurant_id=restaurant.id, phone=user_phone,
                user_name=user_name, cart=result["cart"], address=result.get("address"),
            )
            order_id = created["order_id"]
            actions.append({
                "type": "create_order", "order_id": order_id,
                "payment_url": created.get("payment_url"),
                "payment_provider": created.get("provider"),
            })
        except Exception as e:
            actions.append({"type": "error", "message": f"Order yaratishda xato: {e}"})
        await ai_agent.finalize_session(db, call_id, ended_reason="confirmed", order_id=order_id)

    if end_call:
        await ai_agent.finalize_session(db, call_id, ended_reason="user_hangup")

    # TTS — javobni audio qilish (faqat TTS provayder yoqilgan bo'lsa)
    reply_text = (result.get("reply") or "").strip()
    audio_b64: Optional[str] = None
    tts_provider = (platform.get("ai_tts_provider") or "openai").lower()
    if reply_text and tts_provider not in ("none", "off", "disabled", ""):
        try:
            voice_id = voice_svc.voice_for_restaurant(restaurant.ai_agent_voice)
            tts_bytes = await voice_svc.synthesize(reply_text, voice=voice_id)
            audio_b64 = base64.b64encode(tts_bytes).decode("ascii")
            if call_id in ai_agent._SESSIONS:
                ai_agent._SESSIONS[call_id].tts_chars += len(reply_text)
        except Exception as e:
            from api.logging_config import log_critical
            log_critical("ai_agent", "TTS failed", error=str(e), restaurant_id=restaurant.id)
            # Audio yo'q bo'lsa ham matn javobni qaytaramiz — bot uni text qilib yuboradi

    return VoiceTurnResponse(
        transcript=transcript,
        reply_text=reply_text,
        reply_audio_b64=audio_b64,
        actions=actions,
        cart=result.get("cart", []),
        address=result.get("address"),
        confirmed=bool(result.get("confirmed")),
        transferred=bool(result.get("transferred")),
        order_id=order_id,
        is_catering=bool(result.get("is_catering")),
        ended_reason=result.get("ended_reason"),
    )


# ── Helpers ──────────────────────────────────────────────────────────────

async def _create_ai_order(
    db: AsyncSession,
    restaurant_id: int,
    phone: str,
    user_name: Optional[str],
    cart: list[dict],
    address: Optional[str],
) -> int:
    """Tasdiqlangan AI savatdan ichki Order yaratadi.

    AI orqali kelgan mijoz `phone:+998...` telegram_id bilan saqlanadi.
    Yetkazib berish/olib ketish: address bo'lsa delivery, aks holda pickup.
    """
    user = await get_or_create_phone_user(db, phone=phone, full_name=user_name)

    total = sum(float(i["price"]) * int(i["quantity"]) for i in cart)
    delivery_type = DeliveryType.delivery if address else DeliveryType.pickup

    # Manzilni geokodlash (ovozdan matn keladi → koordinata)
    lat = lon = None
    if address:
        try:
            from api.services.geocode import geocode_address
            res = await geocode_address(address)
            if res:
                lat, lon = res
        except Exception:
            pass

    # AI telefon zakazi — KARTA (oldindan to'lov, link yuboriladi)
    order = Order(
        user_id=user.id,
        restaurant_id=restaurant_id,
        delivery_type=delivery_type,
        address=address,
        latitude=lat,
        longitude=lon,
        total_price=total,
        delivery_fee=0.0,
        status=OrderStatus.pending,
        order_kind="regular",
        payment_method="card",
        payment_timing="now",
        payment_status="pending",
    )
    db.add(order)
    await db.flush()

    for item in cart:
        db.add(OrderItem(
            order_id=order.id,
            product_id=int(item["product_id"]),
            quantity=int(item["quantity"]),
            price=float(item["price"]),
        ))

    # Karta to'lov linki — yoqilgan birinchi provayder bo'yicha
    payment_url = None
    payment_provider = None
    try:
        from api.services.order_payments import get_enabled_providers, generate_payment_url, make_order_trans_id
        providers = get_enabled_providers(restaurant) if (restaurant := await db.get(Restaurant, restaurant_id)) else []
        if providers:
            order.merchant_trans_id = make_order_trans_id(order.id)
            payment_url, _ = generate_payment_url(restaurant, order, providers[0])
            payment_provider = providers[0]
    except Exception as e:
        from api.logging_config import log_critical
        log_critical("ai_agent", "AI order to'lov link xato", error=str(e), order_id=order.id)

    await db.commit()
    return {"order_id": order.id, "payment_url": payment_url, "provider": payment_provider,
            "lat": lat, "lon": lon}
