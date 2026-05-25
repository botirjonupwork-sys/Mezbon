from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str = ""
    WEBAPP_URL: str = ""
    ADMIN_CHAT_ID: str = ""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/muhsina_somsa"
    REDIS_URL: str = "redis://localhost:6379"

    # Alice POS
    ALICE_API_URL: str = "https://api.alicepos.com/v2"
    ALICE_API_KEY: str = ""
    ALICE_STORE_ID: str = ""

    # Kuryer Bot
    COURIER_BOT_TOKEN: str = ""

    # Yandex Delivery
    YANDEX_DELIVERY_TOKEN: str = ""

    # Admin panel — bularsiz dastur ishga tushmaydi (production-safe)
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""           # .env'da o'rnatilishi SHART
    SECRET_KEY: str = ""               # .env'da o'rnatilishi SHART (256-bit random)

    # Super Admin
    SUPER_ADMIN_USERNAME: str = "superadmin"
    SUPER_ADMIN_PASSWORD: str = ""     # .env'da o'rnatilishi SHART

    # Biznes qoidalari
    DELIVERY_FEE: float = 10000.0
    MIN_ORDER_AMOUNT: float = 20000.0
    WORK_START: str = "09:00"
    WORK_END: str = "22:00"

    # App
    DEBUG: bool = True
    API_URL: str = "http://localhost:8000"

    # Critical alerts (ixtiyoriy) — `log_critical()` shu kanalga ham xabar yuboradi
    ALERT_BOT_TOKEN: str = ""           # Alohida bot tokeni (asosiy bot bilan to'qnashmaslik)
    ALERT_CHAT_ID: str = ""              # Telegram chat/group ID (number yoki @username)
    ALERT_DEDUP_SECONDS: int = 300       # Bir xil xato shu davrda qayta yuborilmaydi

    class Config:
        env_file = ".env"
        extra = "ignore"  # .env da qo'shimcha variable bo'lsa e'tiborsiz


settings = Settings()


# Production xavfsizlik tekshiruvi: kritik secret'lar bo'sh bo'lsa app yopiladi.
# Test rejim (TESTING=1) bunga ta'sir qilmaydi.
import os as _os
_TESTING = _os.getenv("TESTING") == "1"
if not _TESTING:
    _missing = []
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 16:
        _missing.append("SECRET_KEY (kamida 16 belgi)")
    if not settings.ADMIN_PASSWORD:
        _missing.append("ADMIN_PASSWORD")
    if not settings.SUPER_ADMIN_PASSWORD:
        _missing.append("SUPER_ADMIN_PASSWORD")
    if _missing:
        raise RuntimeError(
            "Kritik xavfsizlik konfiguratsiyasi yetishmaydi! .env'ga qo'shing: "
            + ", ".join(_missing)
        )
