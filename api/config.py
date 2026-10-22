from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str = "8303328779:AAGBlD6jLjl8qESXnU8Q-CqZ_WhRwgvJ13c"
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
    COURIER_BOT_TOKEN: str = "8751215042:AAG0V3zO922SEKp18p91Ujva_oJAsK-eGas"

    # Yandex Delivery
    YANDEX_DELIVERY_TOKEN: str = ""

    # Admin panel — bularsiz dastur ishga tushmaydi (production-safe)
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"           # .env'da o'rnatilishi SHART
    SECRET_KEY: str = ""               # .env'da o'rnatilishi SHART (256-bit random)

    # Super Admin
    SUPER_ADMIN_USERNAME: str = "superadmin"
    SUPER_ADMIN_PASSWORD: str = "superadmin123"     # .env'da o'rnatilishi SHART

    # Bot<->API ichki autentifikatsiya — SECRET_KEY'dan AJRATILGAN (audit C1).
    # Bo'sh bo'lsa bot so'rovlari rad etiladi (fail-closed). .env va bot bir xil qiymat.
    BOT_API_SECRET: str = ""

    # Payme Subscribe — saqlangan karta tokenlarini shifrlash master-kaliti (Fernet).
    # Bu kalit DB'dan AJRATILGAN holda env'da turishi SHART (token'lar DB'da, kalit env'da).
    # Yaratish: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Autopay ishlatilmasa bo'sh bo'lishi mumkin; ishlatilganда bo'sh bo'lsa shifrlash xato beradi.
    PAYME_TOKEN_ENC_KEY: str = ""

    # Biznes qoidalari
    DELIVERY_FEE: float = 10000.0
    MIN_ORDER_AMOUNT: float = 20000.0
    WORK_START: str = "09:00"
    WORK_END: str = "22:00"

    # App
    DEBUG: bool = False               # default False (audit H1) — prod xavfsiz
    SQL_ECHO: bool = False             # SQL echo alohida (DEBUG'dan ajratilgan) — odatda False
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
