from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.database import create_tables
from api.logging_config import setup_logging
from api.services import platform
from api.routes import (
    users, menu, orders, reviews, admin, auth, couriers, superadmin, branches,
    catering, billing, ai, health, super_admin, super_legacy, pos,
    telegram_payments, registration, yandex_webhook,
)

# Logging — eng birinchi sozlanishi shart (boshqa modullar import paytida ham log yozishi mumkin)
setup_logging()

# Rate limiter (IP bo'yicha)
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    os.makedirs("static/images/products", exist_ok=True)

    # ── APScheduler — daily 10:00 subscription check ──
    # ENABLE_SCHEDULER=1 (yoki DEBUG=False) bo'lsa avtomatik yoqiladi
    from api.services.scheduler import start_scheduler, shutdown_scheduler
    start_scheduler()

    yield

    shutdown_scheduler()


app = FastAPI(
    title="Muhsina Dollar Somsa API",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — faqat ruxsat etilgan origin'lar
ALLOWED_ORIGINS = [
    "https://restaurant.tursunboyev.com",
    "https://super.tursunboyev.com",
    "http://localhost:5173",  # Admin panel dev
    "http://localhost:5174",  # Super admin dev (eski)
    "http://localhost:3001",  # Super admin dev (vite)
    "http://localhost:3000",
]
# Kerak bo'lsa .env orqali qo'shimcha origin qo'shish
_extra = os.getenv("CORS_EXTRA_ORIGINS", "")
if _extra:
    ALLOWED_ORIGINS.extend([o.strip() for o in _extra.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# ── Maintenance mode middleware ──────────────────────────────────────────
# Super-admin yoqib qo'ysa — barcha so'rovlar 503 qaytaradi, faqat super-admin
# o'zi va monitoring uchun zarur endpointlar ishlaydi.

_MAINTENANCE_ALLOW_PREFIXES = (
    "/super-admin",       # super o'zi maintenance'ni o'chirishi uchun
    "/auth/super/login",  # super qayta kirishi uchun
    "/auth/login",        # admin login (super buyrug'iga qaytishi mumkin)
    "/health",            # monitoring
    "/static",            # rasmlar
    "/docs", "/openapi.json", "/redoc",  # API docs
)


# ── Webhook latency tracker (Faza 7) ─────────────────────────────────────


_WEBHOOK_KEY_MAP = {
    "/payments/click/webhook": "click",
    "/payments/payme/webhook": "payme",
    "/payments/telegram/prepare": "telegram_prepare",
    "/payments/telegram/precheck": "telegram_precheck",
    "/payments/telegram/confirm": "telegram_confirm",
    "/webhooks/yandex": "yandex_delivery",
}


@app.middleware("http")
async def webhook_metrics_middleware(request: Request, call_next):
    import time as _t
    path = request.url.path
    key = _WEBHOOK_KEY_MAP.get(path)
    if not key:
        return await call_next(request)
    t0 = _t.perf_counter()
    error = None
    response = None
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        error = type(e).__name__
        raise
    finally:
        try:
            from api.services import webhook_metrics
            webhook_metrics.record(
                endpoint_key=key,
                duration_ms=(_t.perf_counter() - t0) * 1000,
                status_code=response.status_code if response else 500,
                path=path,
                error=error,
            )
        except Exception:
            pass


@app.middleware("http")
async def maintenance_guard(request: Request, call_next):
    if platform.is_maintenance():
        path = request.url.path
        if not any(path.startswith(p) for p in _MAINTENANCE_ALLOW_PREFIXES):
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "maintenance_mode",
                    "message": platform.get(
                        "maintenance_message",
                        "Texnik tanaffus. Tez orada qaytamiz.",
                    ),
                },
                headers={"Retry-After": "60"},
            )
    return await call_next(request)


# ── Subscription suspended guard ─────────────────────────────────────────
# Restoran suspended bo'lsa (10 kun grace tugagan), uning API'lari yopiladi —
# foydalanuvchi faqat /admin/billing/* va auth orqali qayta tarif sotib olishi mumkin.

_SUSPENSION_ALLOW_PREFIXES = (
    "/admin/billing",       # tarif sotib olish — yagona yo'l
    "/payments/",           # to'lov yaratish va webhook
    "/auth/",               # login/refresh
    "/super-admin/",        # super-admin har doim ishlaydi
    "/super/",              # super legacy
    "/health",
    "/static/",
    "/docs",
    "/openapi.json",
    "/redoc",
)


@app.middleware("http")
async def subscription_guard(request: Request, call_next):
    """Suspended restoranlar uchun 402 Payment Required.

    JWT/legacy token'dan rid'ni o'qib, Restaurant.subscription_status='suspended'
    bo'lsa, allow-list tashqarisidagi har endpoint 402 qaytaradi.

    Performance eslatma: har request'da bitta DB query (faqat suspended uchun).
    Yuqori scale paytida cache (Redis) qo'shish kerak.
    """
    path = request.url.path
    if any(path.startswith(p) for p in _SUSPENSION_ALLOW_PREFIXES):
        return await call_next(request)

    # Token yo'q bo'lsa — tekshirish kerak emas (boshqa middleware/dep ishlaydi)
    auth = request.headers.get("authorization") or ""
    if not auth:
        return await call_next(request)

    # Tezkor tekshiruv — faqat token mavjud bo'lsa
    try:
        from api.auth_deps import _parse_token
        ctx = _parse_token(auth)
        if not ctx or ctx.is_super or not ctx.restaurant_id:
            return await call_next(request)

        from api.database import AsyncSessionLocal
        from sqlalchemy import select
        from database.models import Restaurant
        async with AsyncSessionLocal() as db:
            status = (await db.execute(
                select(Restaurant.subscription_status).where(Restaurant.id == ctx.restaurant_id)
            )).scalar_one_or_none()
            if status == "suspended":
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail": {
                            "code": "subscription_suspended",
                            "message": "Imtiyozli davr tugadi. Hizmatni tiklash uchun "
                                       "tarif uchun to'lov qiling.",
                            "billing_url": "/admin/billing/upgrade",
                        }
                    },
                )
    except Exception:
        # Middleware xato bersa, asosiy oqimga to'sqinlik qilmaslik
        pass

    return await call_next(request)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(users.public_router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(reviews.router)
app.include_router(admin.router)
app.include_router(couriers.router)
app.include_router(branches.router)
app.include_router(catering.router)
app.include_router(billing.router)
app.include_router(ai.router)
app.include_router(health.router)
app.include_router(super_admin.router)
app.include_router(super_legacy.router)
app.include_router(pos.router)
app.include_router(telegram_payments.router)
app.include_router(registration.router)
app.include_router(yandex_webhook.router)
from api.routes import legal  # noqa: E402
app.include_router(legal.router)

# Static fayllar (rasmlar)
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return {"status": "ok", "project": "Muhsina Dollar Somsa"}
