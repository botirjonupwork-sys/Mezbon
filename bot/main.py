import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from bot.handlers import start, menu, cart, order, review, profile

load_dotenv()


async def main():
    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        raise ValueError("BOT_TOKEN .env faylida yo'q!")

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(cart.router)
    dp.include_router(order.router)
    dp.include_router(review.router)
    dp.include_router(profile.router)

    print("🥟 Muhsina Dollar Somsa bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
