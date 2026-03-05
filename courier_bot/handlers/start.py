import os
import httpx
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

API_URL = os.getenv("API_URL", "http://localhost:8000")


class CourierReg(StatesGroup):
    full_name = State()
    phone = State()
    transport = State()


def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Faol zakazlar")],
            [KeyboardButton(text="📊 Mening statistikam")],
        ],
        resize_keyboard=True,
    )


def transport_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Avtomobil"), KeyboardButton(text="🏍 Motosikl")],
            [KeyboardButton(text="🚲 Velosiped"), KeyboardButton(text="🚶 Piyoda")],
        ],
        resize_keyboard=True,
    )


TRANSPORT_MAP = {
    "🚗 Avtomobil": "car",
    "🏍 Motosikl": "motorcycle",
    "🚲 Velosiped": "bicycle",
    "🚶 Piyoda": "walk",
}


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    tg_id = str(message.from_user.id)

    # Kuryer bazada bormi?
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_URL}/couriers/{tg_id}")
            if r.status_code == 200:
                courier = r.json()
                status = courier.get("status")
                if status == "active":
                    await message.answer(
                        f"Salom, {courier['full_name']}! 👋\n"
                        "Siz faol kuryer sifatida ro'yxatdan o'tgansiz.\n\n"
                        "Yangi zakazlar avtomatik keladi!",
                        reply_markup=main_menu_kb(),
                    )
                elif status == "pending":
                    await message.answer(
                        "⏳ Sizning arizangiz ko'rib chiqilmoqda.\n"
                        "Admin tasdiqlashi kutilmoqda.",
                    )
                else:
                    await message.answer("🚫 Sizning hisobingiz bloklangan.")
                return
    except Exception:
        pass

    # Ro'yxatdan o'tish
    await message.answer(
        "🚗 <b>Kuryer bo'lib ishlash</b>\n\n"
        "Ro'yxatdan o'tish uchun ismingizni kiriting:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(CourierReg.full_name)


@router.message(CourierReg.full_name)
async def enter_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await message.answer(
        "📱 Telefon raqamingizni kiriting:\n"
        "<i>Masalan: +998901234567</i>"
    )
    await state.set_state(CourierReg.phone)


@router.message(CourierReg.phone)
async def enter_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+998") or len(phone) != 13:
        await message.answer("⚠️ Telefon +998XXXXXXXXX formatida bo'lishi kerak!")
        return
    await state.update_data(phone=phone)
    await message.answer(
        "🚗 Transport turini tanlang:",
        reply_markup=transport_kb(),
    )
    await state.set_state(CourierReg.transport)


@router.message(CourierReg.transport, F.text.in_(TRANSPORT_MAP.keys()))
async def enter_transport(message: Message, state: FSMContext):
    data = await state.get_data()
    transport = TRANSPORT_MAP[message.text]

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API_URL}/couriers/register",
                json={
                    "telegram_id": str(message.from_user.id),
                    "full_name": data["full_name"],
                    "phone": data["phone"],
                    "transport_type": transport,
                },
            )
            if r.status_code == 200:
                await message.answer(
                    "✅ Arizangiz qabul qilindi!\n\n"
                    "⏳ Admin tasdiqlashini kuting.\n"
                    "Tasdiqlanganingizda xabar beramiz!",
                    reply_markup=ReplyKeyboardRemove(),
                )
            else:
                await message.answer(
                    f"⚠️ Xatolik: {r.text}",
                    reply_markup=ReplyKeyboardRemove(),
                )
    except Exception:
        await message.answer(
            "⚠️ Server bilan bog'lanishda xato!",
            reply_markup=ReplyKeyboardRemove(),
        )

    await state.clear()
