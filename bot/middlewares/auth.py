"""Bot middleware — foydalanuvchi ma'lumotlarini request ga qo'shish"""
from typing import Callable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from bot.api_client import get_user


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            user = await get_user(str(event.from_user.id))
            data["db_user"] = user
        return await handler(event, data)
