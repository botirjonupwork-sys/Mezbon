import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from courier_bot.handlers import start, orders
from courier_bot.middlewares.service_gate import ServiceGateMiddleware

load_dotenv()


async def main():
    bot_token = os.getenv("COURIER_BOT_TOKEN", "")
    if not bot_token:
        raise ValueError("COURIER_BOT_TOKEN .env faylida yo'q!")

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Restoran bloklangan/suspended bo'lsa kuryer ham xizmat ko'rsatmaydi
    gate = ServiceGateMiddleware()
    dp.message.middleware(gate)
    dp.callback_query.middleware(gate)

    dp.include_router(start.router)
    dp.include_router(orders.router)

    print("🚗 Kuryer bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
