from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.database import create_tables
from api.routes import users, menu, orders, reviews, admin, auth, couriers, superadmin, branches, catering

# Rate limiter (IP bo'yicha)
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    # Rasm papkasini yaratamiz
    os.makedirs("static/images/products", exist_ok=True)
    yield


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
    "http://localhost:5174",  # Super admin dev
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

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(reviews.router)
app.include_router(admin.router)
app.include_router(couriers.router)
app.include_router(branches.router)
app.include_router(catering.router)

# Static fayllar (rasmlar)
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return {"status": "ok", "project": "Muhsina Dollar Somsa"}
