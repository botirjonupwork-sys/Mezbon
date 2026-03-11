"""Admin login — .env va admins.json dan tekshiradi"""
import os
import json
import hashlib
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from api.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

ADMINS_FILE = "admins.json"


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    name: str
    is_super: bool = False


def _load_admins() -> list:
    if not os.path.exists(ADMINS_FILE):
        return []
    try:
        with open(ADMINS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest):
    # 1. .env dagi super admin
    if data.username == settings.ADMIN_USERNAME and data.password == settings.ADMIN_PASSWORD:
        return LoginResponse(token=settings.SECRET_KEY, name=data.username, is_super=True)

    # 2. admins.json dagi oddiy adminlar
    admins = _load_admins()
    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    for admin in admins:
        if admin["username"] == data.username and admin["password"] == hashed:
            return LoginResponse(token=settings.SECRET_KEY, name=data.username, is_super=False)

    raise HTTPException(401, "Login yoki parol noto'g'ri")
