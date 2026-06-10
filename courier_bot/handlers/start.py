import os
import httpx
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

API_URL = os.getenv("API_URL", "http://localhost:8000")
_BOT_HEADERS = {"X-Bot-Secret": os.getenv("BOT_API_SECRET", "")}
# Bot manager har bir restoran kuryer botini BOT_RESTAURANT_ID bilan spawn qiladi.
# Bu botning kuryeri FAQAT shu restoran filiallarini ko'rishi/ro'yxatdan o'tishi
# shart — aks holda restoran #5 kuryeri restoran #1 filialiga bog'lanib qoladi.
COURIER_RESTAURANT_ID = int(os.getenv("BOT_RESTAURANT_ID") or "1")


class CourierReg(StatesGroup):
    full_name = State()
    phone = State()
    transport = State()
    branch_location = State()


def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Faol zakazlar")],
            [KeyboardButton(text="📊 Mening statistikam")],
            [KeyboardButton(text="📍 Filial o'zgartirish")],
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


def branch_location_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


TRANSPORT_MAP = {
    "🚗 Avtomobil": "car",
    "🏍 Motosikl": "motorcycle",
    "🚲 Velosiped": "bicycle",
    "🚶 Piyoda": "walk",
}


async def _get_nearest_branches(lat: float, lon: float):
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{API_URL}/branches/nearest",
                params={"lat": lat, "lon": lon, "restaurant_id": COURIER_RESTAURANT_ID},
                timeout=5.0,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return []


def branches_kb(branches: list) -> InlineKeyboardMarkup:
    buttons = []
    for b in branches:
        status = "✅" if b.get("is_open") else "❌"
        label = f"{status} {b['name']} ({b['distance_km']} km)"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"cbranch:{b['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    tg_id = str(message.from_user.id)

    # Kuryer bazada bormi?
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_URL}/couriers/{tg_id}", headers=_BOT_HEADERS)
            if r.status_code == 200:
                courier = r.json()
                status = courier.get("status")
                if status == "active":
                    # Filial tanlangan bo'lsa saqlash
                    if courier.get("branch_id"):
                        await state.update_data(
                            branch_id=courier["branch_id"],
                        )
                    await message.answer(
                        f"Salom, {courier['full_name']}! 👋\n"
                        "Siz faol kuryer sifatida ro'yxatdan o'tgansiz.\n\n"
                        "Yangi zakazlar avtomatik keladi!",
                        reply_markup=main_menu_kb(),
                    )
                elif status == "pending":
                    await message.answer(
                        "⏳ Sizning arizangiz ko'rib chiqilmoqda.\n"
                        "Admin tasdiqlashini kuting.",
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
        parse_mode="HTML",
    )
    await state.set_state(CourierReg.full_name)


@router.message(CourierReg.full_name)
async def enter_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await message.answer(
        "📱 Telefon raqamingizni kiriting:\n"
        "<i>Masalan: +998901234567</i>",
        parse_mode="HTML",
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
    await state.update_data(transport=TRANSPORT_MAP[message.text])
    await message.answer(
        "📍 Qaysi filialda ishlaysiz?\n"
        "Yaqin filiallarni topish uchun joylashuvingizni yuboring:",
        reply_markup=branch_location_kb(),
    )
    await state.set_state(CourierReg.branch_location)


@router.message(CourierReg.branch_location, F.location)
async def enter_branch_location(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude

    branches = await _get_nearest_branches(lat, lon)
    if not branches:
        await message.answer(
            "😔 Filiallar topilmadi. Qaytadan urinib ko'ring.",
            reply_markup=branch_location_kb(),
        )
        return

    text = "📍 <b>Yaqin filiallar:</b>\n\n"
    for b in branches[:5]:
        status = "✅ Ochiq" if b.get("is_open") else "❌ Yopiq"
        text += f"🏪 <b>{b['name']}</b> — {b['distance_km']} km ({status})\n"

    text += "\nQaysi filialda ishlashni xohlaysiz?"
    await message.answer(text, reply_markup=branches_kb(branches[:5]), parse_mode="HTML")


@router.callback_query(F.data.startswith("cbranch:"))
async def branch_selected_reg(callback: CallbackQuery, state: FSMContext):
    branch_id = int(callback.data.split(":")[1])
    data = await state.get_data()

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API_URL}/couriers/register",
                json={
                    "telegram_id": str(callback.from_user.id),
                    "full_name": data["full_name"],
                    "phone": data["phone"],
                    "transport_type": data["transport"],
                    "branch_id": branch_id,
                },
                headers=_BOT_HEADERS,
            )
            if r.status_code == 200:
                await callback.message.answer(
                    "✅ Arizangiz qabul qilindi!\n\n"
                    "⏳ Admin tasdiqlashini kuting.\n"
                    "Tasdiqlanganingizda xabar beramiz!",
                    reply_markup=ReplyKeyboardRemove(),
                )
            else:
                await callback.message.answer(
                    f"⚠️ Xatolik: {r.text}",
                    reply_markup=ReplyKeyboardRemove(),
                )
    except Exception:
        await callback.message.answer(
            "⚠️ Server bilan bog'lanishda xato!",
            reply_markup=ReplyKeyboardRemove(),
        )

    await state.clear()
    await callback.answer()


# ── Filial o'zgartirish ───────────────────────────────

@router.message(F.text == "📍 Filial o'zgartirish")
async def change_branch(message: Message):
    await message.answer(
        "📍 Yangi filialga o'tish uchun joylashuvingizni yuboring:",
        reply_markup=branch_location_kb(),
    )


@router.message(F.location)
async def location_for_branch_change(message: Message, state: FSMContext):
    """Filial o'zgartirish uchun joylashuv."""
    current_state = await state.get_state()
    if current_state and "CourierReg" in current_state:
        return

    lat = message.location.latitude
    lon = message.location.longitude

    branches = await _get_nearest_branches(lat, lon)
    if not branches:
        await message.answer("😔 Filiallar topilmadi.", reply_markup=main_menu_kb())
        return

    text = "📍 <b>Yaqin filiallar:</b>\n\nQaysi filialga o'tmoqchisiz?"
    await message.answer(text, reply_markup=branches_kb(branches[:5]), parse_mode="HTML")


@router.callback_query(F.data.startswith("cbranch:"))
async def branch_changed(callback: CallbackQuery, state: FSMContext):
    """Filial o'zgartirish — faqat active kuryerlar uchun."""
    current_state = await state.get_state()
    if current_state and "CourierReg" in current_state:
        return  # Ro'yxatdan o'tish jarayonida bo'lsa, boshqa handler ishlaydi

    branch_id = int(callback.data.split(":")[1])
    await state.update_data(branch_id=branch_id)

    # Backendga ham yuborish
    tg_id = str(callback.from_user.id)
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{API_URL}/couriers/{tg_id}/branch",
                params={"branch_id": branch_id},
                headers=_BOT_HEADERS,
                timeout=5.0,
            )
    except Exception:
        pass

    await callback.message.answer(
        "✅ Filial o'zgartirildi! Endi shu filialning zakazlari keladi.",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
