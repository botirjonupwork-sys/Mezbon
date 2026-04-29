from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum, JSON
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

    plan = Column(String, default="free")  # Backward compat — plan slug
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)  # Yangi: tariflar bilan FK
    plan_expires_at = Column(DateTime, nullable=True)  # Tarif amal qilish muddati (None = cheksiz/Free)
    status = Column(String, default="active")
    commission_percent = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    payment_card_number = Column(String)
    payment_card_name = Column(String)
    payment_card_bank = Column(String)

    # Dastavka provider: "own" (o'z kuryerlari) | "yandex" | "customer_choice"
    delivery_provider = Column(String, default="own")
    yandex_api_token = Column(String)
    yandex_test_mode = Column(Boolean, default=True)

    # Valyuta kursi (USD → UZS) catering uchun
    currency_auto = Column(Boolean, default=True)    # True: CBU API, False: qo'lda
    currency_rate_manual = Column(Float, default=12500.0)
    currency_rate_cache = Column(Float)              # CBU dan oxirgi kurs
    currency_cache_updated_at = Column(DateTime)     # Cache vaqti
    # To'lov karta raqami (catering "hozir to'lov" uchun)
    catering_payment_card = Column(String)
    catering_payment_owner = Column(String)

    # Catering guruhlari minimal va step
    catering_somsa_min = Column(Integer, default=100)
    catering_somsa_step = Column(Integer, default=1)
    catering_nan_min = Column(Integer, default=40)
    catering_nan_step = Column(Integer, default=40)
    # Dastavka km narxi (har restaurant uchun)
    catering_delivery_per_km_uzs = Column(Float, default=5000.0)

    # Click merchant API
    click_merchant_id = Column(String)
    click_service_id = Column(String)
    click_secret_key = Column(String)
    click_enabled = Column(Boolean, default=False)

    # Payme merchant API
    payme_merchant_id = Column(String)
    payme_secret_key = Column(String)
    payme_enabled = Column(Boolean, default=False)

    # AI Call Operator (faqat Pro tarif)
    ai_agent_enabled = Column(Boolean, default=False)
    ai_agent_prompt = Column(Text)              # Restoran uchun maxsus system-prompt prefiksi
    ai_agent_voice = Column(String, default="female")   # 'male' | 'female'
    ai_agent_provider = Column(String, default="openai")  # 'openai' | 'vapi' | 'retell'
    ai_agent_model = Column(String, default="gpt-4o-mini")
    ai_agent_api_key = Column(String)           # Restoran o'z kalitini kiritsa shu, aks holda env

    # POS / Printer integratsiyasi (Hybrid Connect)
    # 'NONE' | 'NEONALISA' | 'GENERIC_ANDROID' | 'BLUETOOTH_PRINTER'
    pos_system_type = Column(String, default="NONE")
    # Har bir POS turi uchun maxsus sozlamalar (api_key, terminal_ip, printer_mac, ...)
    # Postgres'da JSONB, SQLite'da TEXT — SQLAlchemy JSON dialektga moslab tanlaydi.
    pos_config = Column(JSON, default=dict)

    branches = relationship("Branch", back_populates="restaurant")
    plan_obj = relationship("Plan", back_populates="restaurants", foreign_keys=[plan_id])


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
    selected_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    selected_branch = relationship("Branch", foreign_keys=[selected_branch_id])
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

    # ── Catering (tadbir uchun) maydonlar ────────────────
    # product_type: 'regular' (oddiy) | 'catering' (tadbir uchun)
    product_type = Column(String, default="regular")
    # catering_group: 'somsa' | 'nan' — aralash zakaz uchun guruh
    catering_group = Column(String)
    # unit_type: 'piece' (dona) | 'bunch_100' (100 dona) | 'tandir_40' (40 dona/tandir)
    unit_type = Column(String, default="piece")
    min_quantity = Column(Integer, default=1)      # Alohida mahsulot uchun min (ixtiyoriy)
    quantity_step = Column(Integer, default=1)     # Alohida qadam (ixtiyoriy)
    # Dona narxi (catering uchun)
    unit_price_usd = Column(Float)                 # 1 dona USD narx (aralash orders)
    unit_price_pickup_uzs = Column(Float)          # 1 dona saboy so'm narx
    # Eski maydonlar (backward compat)
    price_onsite_usd = Column(Float)
    price_pickup_uzs = Column(Float)
    price_delivery_uzs = Column(Float)
    price_per_km_uzs = Column(Float)

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
    yandex_status = Column(String)
    yandex_tracking_url = Column(String)
    yandex_price = Column(Float)
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

    # ── Catering (tadbir) buyurtma maydonlari ────────────
    order_kind = Column(String, default="regular")   # 'regular' | 'catering'
    schedule_date = Column(String)                    # YYYY-MM-DD
    schedule_time = Column(String)                    # HH:MM
    # Catering delivery turi: 'onsite' | 'pickup' | 'delivery'
    delivery_subtype = Column(String)
    # To'lov maydonlari
    payment_method = Column(String, default="cash")   # 'cash' | 'card'
    payment_timing = Column(String, default="later")  # 'now' | 'later'
    payment_status = Column(String, default="pending")  # 'pending' | 'paid'
    # Buyurtma vaqtidagi valyuta kursi (tarix uchun)
    currency_rate_snapshot = Column(Float)
    # USD'dagi narx (catering uchun)
    total_price_usd = Column(Float)

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


# ── Admin (sub-admin tizimi) ────────────────────────

class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    username = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="admin")
    created_at = Column(DateTime, default=datetime.utcnow)


class CateringSubscriber(Base):
    """Catering bot'ga /start bosgan foydalanuvchilar va guruhlar.

    Har kuni 20:00 da ertangi kun catering buyurtmalari shu obunachilarga yuboriladi.
    chat_type: 'private' (foydalanuvchi) yoki 'group'/'supergroup' (guruh)
    """
    __tablename__ = "catering_subscribers"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True, default=1)
    chat_id = Column(String, unique=True, nullable=False)
    chat_type = Column(String, default="private")
    title = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Platform (SaaS) ─────────────────────────────────

class Plan(Base):
    """SaaS tariflar — restoran qaysi funksiyalardan foydalana olishini belgilaydi.

    Booleanflag'lar PostgreSQL va SQLite ikkalasida ham ishlaydi.
    `order_limit=0` cheksiz degan ma'noni anglatadi.
    """
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    description = Column(Text)
    monthly_price = Column(Float, nullable=False, default=0.0)
    commission_percent = Column(Float, nullable=False, default=0.0)
    # Funksional bayroqlar — feature gating uchun
    has_catering = Column(Boolean, nullable=False, default=False)
    has_ai_agent = Column(Boolean, nullable=False, default=False)
    has_yandex = Column(Boolean, nullable=False, default=False)
    order_limit = Column(Integer, nullable=False, default=0)  # 0 = cheksiz
    # Eski JSON features (backward compat)
    features = Column(Text, default="[]")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    restaurants = relationship("Restaurant", back_populates="plan_obj")


class Payment(Base):
    """SaaS tarif uchun to'lov yozuvi.

    Pul `amount_tiyin` (int) sifatida saqlanadi — 1 so'm = 100 tiyin.
    Click/Payme API'lari tiyin bilan ishlaydi, suzuvchi nuqta xatosi yo'q.
    """
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    # int (tiyin) — float emas, masalan 500,000 so'm = 50,000,000 tiyin
    amount_tiyin = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending | success | failed
    provider = Column(String, nullable=False)                   # click | payme
    external_id = Column(String, nullable=True)                 # provayder tomonidan transaction id
    payment_url = Column(String, nullable=True)                 # mijoz to'lov sahifasi URL'i
    merchant_trans_id = Column(String, unique=True, nullable=True)  # bizning order_id (idempotency)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)


class SuperAdminAction(Base):
    """Super-admin har bir harakatining audit log'i.

    Bu jadvalga har bir status o'zgarishi, plan o'zgartirish, maintenance
    yoki global sozlama o'zgarishi yoziladi. O'chirib bo'lmaydi (faqat
    insert) — manipulyatsiyani aniqlash uchun.
    """
    __tablename__ = "super_admin_actions"

    id = Column(Integer, primary_key=True)
    actor = Column(String, nullable=False)              # super-admin login
    action = Column(String, nullable=False)             # 'restaurant.update' | 'maintenance.set' | ...
    target_type = Column(String, nullable=True)        # 'restaurant' | 'plan' | 'platform' | None
    target_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)               # JSON ko'rinishida (eski/yangi qiymatlar)
    ip = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


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
