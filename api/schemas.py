from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from database.models import OrderStatus, DeliveryType


# ── User ──────────────────────────────────────────────
class UserCreate(BaseModel):
    telegram_id: str
    full_name: str
    phone: str
    language: str = "uz"


class UserOut(BaseModel):
    id: int
    telegram_id: str
    full_name: str
    phone: str
    language: str
    selected_branch_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Address ───────────────────────────────────────────
class AddressCreate(BaseModel):
    title: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class AddressOut(AddressCreate):
    id: int

    class Config:
        from_attributes = True


# ── Category ──────────────────────────────────────────
class CategoryOut(BaseModel):
    id: int
    name_uz: str
    name_ru: Optional[str] = None
    order: int

    class Config:
        from_attributes = True


# ── Product ───────────────────────────────────────────
class ProductOut(BaseModel):
    id: int
    name_uz: str
    name_ru: Optional[str] = None
    description_uz: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    has_time_limit: bool
    available_from: Optional[str] = None
    available_until: Optional[str] = None
    is_stop: bool
    category_id: int

    class Config:
        from_attributes = True


# ── Order ─────────────────────────────────────────────
class OrderItemCreate(BaseModel):
    product_id: int
    # gt=0: manfiy/nol miqdor manfiy umumiy summa beradi (audit H7)
    quantity: int = Field(gt=0, le=1000)


class OrderCreate(BaseModel):
    delivery_type: DeliveryType
    address: Optional[str] = None
    comment: Optional[str] = None
    payment_method: str = "cash"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    delivery_fee: Optional[float] = Field(default=None, ge=0)
    branch_id: Optional[int] = None
    items: List[OrderItemCreate]
    # Faza 10: Dastavka vaqti — "now" yoki "HH:MM" (masalan "15:30")
    delivery_time_slot: Optional[str] = None


class OrderItemOut(BaseModel):
    product_id: int
    quantity: int
    price: float

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    status: OrderStatus
    delivery_type: DeliveryType
    address: Optional[str] = None
    comment: Optional[str] = None
    total_price: float
    delivery_fee: float
    created_at: datetime
    items: List[OrderItemOut]
    # Faza 4: to'lov holati mijoz UI'sida ko'rinishi uchun
    payment_status: Optional[str] = None
    payment_method: Optional[str] = None
    payment_provider: Optional[str] = None
    payment_charge_id: Optional[str] = None
    paid_amount_tiyin: Optional[int] = None

    class Config:
        from_attributes = True


# ── Review ────────────────────────────────────────────
class ReviewCreate(BaseModel):
    rating: int
    comment: Optional[str] = None


class ReviewOut(ReviewCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ── Stop list ─────────────────────────────────────────
class StopUpdate(BaseModel):
    is_stop: bool
