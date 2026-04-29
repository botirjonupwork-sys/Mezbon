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

    # Admin panel
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    SECRET_KEY: str = "muhsina-secret-key-change-in-production"

    # Super Admin
    SUPER_ADMIN_USERNAME: str = "superadmin"
    SUPER_ADMIN_PASSWORD: str = "SuperAdmin2024!"

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
