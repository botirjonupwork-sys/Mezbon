from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.sql import func
from datetime import datetime
import enum


class Base(DeclarativeBase):
    pass


# ── Enums ────────────────────────────────────────────

class OrderStatus(enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    preparing = "preparing"
    ready = "ready"
    delivering = "delivering"
    delivered = "delivered"
    cancelled = "cancelled"


class DeliveryType(enum.Enum):
    delivery = "delivery"
    pickup = "pickup"


class CourierStatus(enum.Enum):
    pending = "pending"
    active = "active"
    blocked = "blocked"


# ── Restaurant (SaaS) ───────────────────────────────

class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    logo_url = Column(String)
    address = Column(String)
    phone = Column(String)

    bot_token = Column(String)
    courier_bot_token = Column(String)

    admin_username = Column(String, default="admin")
    admin_password_hash = Column(String)

    work_hours_from = Column(String, default="09:00")
    work_hours_until = Column(String, default="22:00")
    min_order = Column(Float, default=30000)
    delivery_base_fee = Column(Float, default=10000)
    delivery_per_km = Column(Float, default=3000)
    restaurant_lat = Column(Float, default=41.2995)
    restaurant_lon = Column(Float, default=69.2401)

    plan = Column(String, default="free")
    status = Column(String, default="active")
    commission_percent = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    payment_card_number = Column(String)
    payment_card_name = Column(String)
    payment_card_bank = Column(String)

    branches = relationship("Branch", back_populates="restaurant")


# ── Branch (Filial) ─────────────────────────────────

class Branch(Base):
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    name = Column(String, nullable=False)
    address = Column(String)
    phone = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)

    work_hours_from = Column(String, default="09:00")
    work_hours_until = Column(String, default="22:00")
    min_order = Column(Float, default=30000)
    delivery_base_fee = Column(Float, default=10000)
    delivery_per_km = Column(Float, default=3000)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    restaurant = relationship("Restaurant", back_populates="branches")
    categories = relationship("Category", back_populates="branch")
    products = relationship("Product", back_populates="branch")
    orders = relationship("Order", back_populates="branch")
    couriers = relationship("Courier", back_populates="branch")
    reviews = relationship("Review", back_populates="branch")


# ── User ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    language = Column(String, default="uz")
    created_at = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="user")
    addresses = relationship("Address", back_populates="user")
    reviews = relationship("Review", back_populates="user")


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    address = Column(String, nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)

    user = relationship("User", back_populates="addresses")


# ── Menu ─────────────────────────────────────────────

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True, default=1)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    name_uz = Column(String, nullable=False)
    name_ru = Column(String)
    alice_category_id = Column(String)
    order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    branch = relationship("Branch", back_populates="categories")
    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True, default=1)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    alice_product_id = Column(String)
    category_id = Column(Integer, ForeignKey("categories.id"))
    name_uz = Column(String, nullable=False)
    name_ru = Column(String)
    description_uz = Column(Text)
    description_ru = Column(Text)
    price = Column(Float, nullable=False)
    image_url = Column(String)

    has_time_limit = Column(Boolean, default=False)
    available_from = Column(String)
    available_until = Column(String)

    is_active = Column(Boolean, default=True)
    is_stop = Column(Boolean, default=False)

    branch = relationship("Branch", back_populates="products")
    category = relationship("Category", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")


# ── Orders ───────────────────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True, default=1)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    alice_order_id = Column(String)
    yandex_claim_id = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))
    courier_id = Column(Integer, ForeignKey("couriers.id"), nullable=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.pending)
    delivery_type = Column(Enum(DeliveryType), nullable=False)

    address = Column(String)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    comment = Column(Text)

    total_price = Column(Float, nullable=False)
    delivery_fee = Column(Float, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    branch = relationship("Branch", back_populates="orders")
    user = relationship("User", back_populates="orders")
    courier = relationship("Courier", backref="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


# ── Courier ──────────────────────────────────────────

class Courier(Base):
    __tablename__ = "couriers"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True, default=1)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    telegram_id = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    transport_type = Column(String, default="car")
    status = Column(Enum(CourierStatus), default=CourierStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)

    branch = relationship("Branch", back_populates="couriers")


# ── Review ───────────────────────────────────────────

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True, default=1)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    rating = Column(Integer, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    branch = relationship("Branch", back_populates="reviews")
    user = relationship("User", back_populates="reviews")


# ── Platform (SaaS) ─────────────────────────────────

class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    description = Column(Text)
    monthly_price = Column(Float, default=0.0)
    commission_percent = Column(Float, default=0.0)
    features = Column(Text, default="[]")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CommissionPayment(Base):
    __tablename__ = "commission_payments"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    amount = Column(Float, nullable=False)
    commission_percent = Column(Float, default=0.0)
    orders_revenue = Column(Float, default=0.0)
    period_from = Column(DateTime)
    paid_at = Column(DateTime, default=datetime.utcnow)
    note = Column(String)
    status = Column(String, default="confirmed")
