from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
from api.database import create_tables
from api.routes import users, menu, orders, reviews, admin, auth, couriers, superadmin, branches


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(reviews.router)
app.include_router(admin.router)
app.include_router(couriers.router)
app.include_router(branches.router)

# Static fayllar (rasmlar)
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return {"status": "ok", "project": "Muhsina Dollar Somsa"}
