"""Telegram voice handler — AI operatorga ovoz xabar.

Mijoz bot'ga voice yuboradi → biz audio'ni API'ga uzatamiz → AI javobini audio
qilib qaytaradi → biz uni Telegram'da voice xabar sifatida yuboramiz.

Faqat restoranda `ai_agent_enabled=True` bo'lsa ishlaydi. Tarif `has_ai_agent`
flagini API tomonida tekshiradi (require_plan_feature).
"""
from __future__ import annotations

import base64
import io
import logging

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client


router = Router(name="ai_voice")
log = logging.getLogger("bot.ai_voice")


@router.message(F.voice | F.audio)
async def on_voice(message: Message, bot: Bot):
    """Voice/audio xabarni AI agentga yuborish."""
    user = await api_client.get_user(str(message.from_user.id))
    if not user or not user.get("phone"):
        await message.answer(
            "Ovoz orqali buyurtma berish uchun avval ro'yxatdan o'tib, telefon raqamingizni qoldiring. "
            "/start bosing."
        )
        return

    voice_obj = message.voice or message.audio
    if not voice_obj:
        return

    # Audio'ni Telegram'dan yuklash
    file = await bot.get_file(voice_obj.file_id)
    audio_io = io.BytesIO()
    await bot.download_file(file.file_path, destination=audio_io)
    audio_io.seek(0)
    audio_bytes = audio_io.read()

    if not audio_bytes:
        await message.answer("Audio bo'sh, qayta urinib ko'ring.")
        return

    # AI agentga yuborish — call_id sifatida chat_id ishlatamiz (bir suhbat sessiyasi)
    call_id = f"tg:{message.chat.id}"
    await bot.send_chat_action(message.chat.id, "record_voice")

    try:
        result = await api_client.ai_voice_turn(
            call_id=call_id,
            user_phone=user["phone"],
            audio_bytes=audio_bytes,
            user_name=user.get("full_name", ""),
            filename=f"voice_{voice_obj.file_id[:8]}.ogg",
        )
    except Exception as e:
        log.exception("AI voice-turn xatosi")
        await message.answer(f"AI bilan bog'lanishda xatolik: {e}")
        return

    if "error" in result:
        status = result.get("status", 0)
        if status == 402:
            await message.answer(
                "AI Operator funksiyasi sizning tarifingizda mavjud emas. "
                "Restoran admini tarifni yangilashi kerak."
            )
        elif status == 403:
            await message.answer("AI Operator hozir o'chirilgan.")
        elif status == 400:
            await message.answer(
                "AI Voice ulanmagan. Iltimos, matn orqali yozing yoki keyinroq qayta urinib ko'ring."
            )
        else:
            await message.answer(f"AI xatosi: {result.get('error', 'noma''lum')}")
        return

    # Transcript va AI javobini ko'rsatish
    transcript = (result.get("transcript") or "").strip()
    reply_text = (result.get("reply_text") or "").strip()
    audio_b64 = result.get("reply_audio_b64")

    # Mijoz aytgani — debug uchun ko'rsatish (ixtiyoriy, hayotda olib tashlash mumkin)
    if transcript:
        await message.reply(f"🎙 <i>{transcript}</i>")

    # Audio javob (agar TTS muvaffaqiyatli bo'lgan bo'lsa)
    if audio_b64:
        try:
            audio_bytes_out = base64.b64decode(audio_b64)
            voice_file = BufferedInputFile(audio_bytes_out, filename="reply.ogg")
            await message.answer_voice(voice_file, caption=reply_text[:1024] if reply_text else None)
        except Exception:
            log.exception("Audio javobni yuborish xatosi")
            if reply_text:
                await message.answer(reply_text)
    elif reply_text:
        await message.answer(reply_text)

    # Buyurtma yaratildimi?
    actions = result.get("actions") or []
    for act in actions:
        if act.get("type") == "create_order":
            pay_url = act.get("payment_url")
            provider = (act.get("payment_provider") or "").capitalize()
            if pay_url:
                # To'lov linki — bosiladigan tugma sifatida yuboramiz
                btn_text = f"💳 {provider} orqali to'lash" if provider else "💳 To'lash"
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=btn_text, url=pay_url)
                ]])
                await message.answer(
                    f"✅ Buyurtmangiz qabul qilindi! №{act.get('order_id')}\n"
                    f"To'lov uchun quyidagi tugmani bosing 👇",
                    reply_markup=kb,
                )
            else:
                # To'lov provayderi sozlanmagan — operator bog'lanadi
                await message.answer(
                    f"✅ Buyurtmangiz qabul qilindi! №{act.get('order_id')}\n"
                    f"Tez orada operator siz bilan bog'lanadi."
                )
        elif act.get("type") == "transfer_to_catering":
            await message.answer(
                "📞 Tadbir uchun katta buyurtma — siz bilan operator alohida bog'lanadi."
            )
        elif act.get("type") == "end_call":
            reason = act.get("reason")
            if reason == "conversation_complete":
                pass  # xayrlash AI javobida aytilgan
            elif reason == "outside_work_hours":
                pass  # AI javobida allaqachon aytildi
            elif reason == "time_limit":
                pass
