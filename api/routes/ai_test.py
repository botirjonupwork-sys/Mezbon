"""Super-admin: AI operator SINOV konsoli (telefonsiz, brauzerda ovoz/matn).

Maqsad: real telefon ulanmasdan oldin AI operatorni super-admindan sinash.
Pipeline real telefon bilan BIR XIL (1:1): STT → AI agent → TTS.

Endpointlar (require_superuser):
  POST /super-admin/ai-test/voice  — audio yuborib, audio+matn javob
  POST /super-admin/ai-test/text   — matn yozib, matn(+audio) javob (tez sinov)
  POST /super-admin/ai-test/reset  — sessiyani tozalash

DIQQAT: sinov rejimi — TASDIQLANGAN buyurtma REAL yaratilmaydi (faqat savatcha
qaytariladi), test ma'lumotni ifloslantirmasligi uchun.
"""
from __future__ import annotations

import base64
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.routes.super_admin import require_superuser
from api.services import ai_agent, platform
from api.services import voice as voice_svc
from database.models import Restaurant

router = APIRouter(prefix="/super-admin/ai-test", tags=["super-admin-ai-test"])


async def _get_restaurant(db: AsyncSession, restaurant_id: int) -> Restaurant:
    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")
    return rest


async def _maybe_tts(reply_text: str, rest: Restaurant) -> Optional[str]:
    """TTS provayder yoqilgan bo'lsa audio (base64), aks holda None."""
    tts_provider = (platform.get("ai_tts_provider") or "none").lower()
    if not reply_text or tts_provider in ("none", "off", "disabled", ""):
        return None
    try:
        voice_id = voice_svc.voice_for_restaurant(rest.ai_agent_voice)
        tts_bytes = await voice_svc.synthesize(reply_text, voice=voice_id)
        return base64.b64encode(tts_bytes).decode("ascii")
    except Exception:
        return None  # audio bo'lmasa ham matn qaytadi


def _result_payload(transcript: str, result: dict, audio_b64: Optional[str]) -> dict:
    return {
        "transcript": transcript,
        "reply_text": (result.get("reply") or "").strip(),
        "reply_audio_b64": audio_b64,
        "cart": result.get("cart", []),
        "address": result.get("address"),
        "confirmed": bool(result.get("confirmed")),
        "transferred": bool(result.get("transferred")),
        "is_catering": bool(result.get("is_catering")),
        "ended_reason": result.get("ended_reason"),
        "test_mode": True,  # real buyurtma yaratilmaydi
    }


# ── Ovozli sinov turn ───────────────────────────────────

@router.post("/voice")
async def ai_test_voice(
    restaurant_id: int = Form(...),
    call_id: str = Form(...),
    audio: UploadFile = File(...),
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    rest = await _get_restaurant(db, restaurant_id)
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "Audio bo'sh")
    if len(audio_bytes) > 20 * 1024 * 1024:
        raise HTTPException(413, "Audio juda katta")

    sess = ai_agent.get_session(call_id, rest.id, "+000test")
    lang_hint = voice_svc.language_hint(getattr(rest, "ai_agent_language", None))
    try:
        menu_products = await ai_agent.load_menu(db, rest.id)
        menu_item_names = [p.name_uz for p in menu_products if p.name_uz]
    except Exception:
        menu_item_names = []

    try:
        transcript = await voice_svc.transcribe(
            audio_bytes, filename=audio.filename or "voice.ogg",
            language=lang_hint, menu_items=menu_item_names,
        )
    except Exception as e:
        raise HTTPException(502, f"STT xatosi: {e}")

    if not transcript:
        return {"transcript": "", "reply_text": "Sizni eshitmadim, qaytadan ayting.",
                "reply_audio_b64": None, "test_mode": True}

    result = await ai_agent.process_message(db, rest, sess, transcript)
    audio_b64 = await _maybe_tts((result.get("reply") or "").strip(), rest)
    return _result_payload(transcript, result, audio_b64)


# ── Matnli sinov (tez, mikrofon shart emas) ─────────────

class TextTurnIn(BaseModel):
    restaurant_id: int
    call_id: str
    text: str
    want_audio: bool = False


@router.post("/text")
async def ai_test_text(body: TextTurnIn, actor: dict = Depends(require_superuser),
                       db: AsyncSession = Depends(get_db)):
    rest = await _get_restaurant(db, body.restaurant_id)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "Matn bo'sh")
    sess = ai_agent.get_session(body.call_id, rest.id, "+000test")
    result = await ai_agent.process_message(db, rest, sess, text)
    audio_b64 = await _maybe_tts((result.get("reply") or "").strip(), rest) if body.want_audio else None
    return _result_payload(text, result, audio_b64)


# ── Sessiyani tozalash ──────────────────────────────────

class ResetIn(BaseModel):
    call_id: str


@router.post("/reset")
async def ai_test_reset(body: ResetIn, actor: dict = Depends(require_superuser)):
    ai_agent.end_session(body.call_id)
    return {"ok": True}
