import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from bot.handlers import start, menu, cart, order, review, profile, catering
from bot import api_client

load_dotenv()


async def run_bot(bot_token: str):
    """
    Bitta restoran uchun bot ishga tushirish.
    Bu funksiya ALOHIDA subprocess'da chaqiriladi — global state boshqa botlar bilan
    aralashmaydi, chunki har bir subprocess o'z xotirasiga ega.
    """
    if not bot_token:
        raise ValueError("BOT_TOKEN bo'sh!")

    # API dan restaurant-scoped JWT token olish
    try:
        login_data = await api_client.bot_login(bot_token)
        api_client.set_auth(login_data["token"], login_data["restaurant_id"])
        rid = login_data["restaurant_id"]
        rname = login_data.get("restaurant_name", f"Restoran #{rid}")
        print(f"[Bot] API login: {rname} (restaurant_id={rid})")
    except Exception as e:
        # API hali ishga tushmagan bo'lsa — env dan fallback
        rid = int(os.getenv("BOT_RESTAURANT_ID", "1"))
        rname = f"Restoran #{rid}"
        api_client.set_auth("", rid)
        print(f"[Bot] API bot-login xato: {e}. Fallback: restaurant_id={rid}")

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # FSM state filterlari bor routerlar BIRINCHI — global F.location'lar oldidan
    dp.include_router(catering.router)
    dp.include_router(order.router)
    dp.include_router(review.router)
    dp.include_router(start.router)  # branch tanlash uchun global F.location bor
    dp.include_router(menu.router)
    dp.include_router(cart.router)
    dp.include_router(profile.router)

    print(f"[Bot] Ishga tushdi: {rname} (restaurant_id={rid})")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def main():
    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        raise ValueError("BOT_TOKEN .env faylida yo'q!")
    await run_bot(bot_token)


if __name__ == "__main__":
    asyncio.run(main())
