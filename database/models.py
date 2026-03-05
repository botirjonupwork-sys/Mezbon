from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship, DeclarativeBase
from datetime import datetime
import enum


class Base(DeclarativeBase):
    pass


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
    title = Column(String)  # "Uy", "Ish" va h.k.
    address = Column(String, nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)

    user = relationship("User", back_populates="addresses")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name_uz = Column(String, nullable=False)
    name_ru = Column(String)
    alice_category_id = Column(String)  # Alice POS dan kelgan ID
    order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    alice_product_id = Column(String)   # Alice POS dan kelgan ID
    category_id = Column(Integer, ForeignKey("categories.id"))
    name_uz = Column(String, nullable=False)
    name_ru = Column(String)
    description_uz = Column(Text)
    description_ru = Column(Text)
    price = Column(Float, nullable=False)
    image_url = Column(String)

    # Vaqt limiti
    has_time_limit = Column(Boolean, default=False)
    available_from = Column(String)  # "09:00"
    available_until = Column(String)  # "22:00"

    is_active = Column(Boolean, default=True)
    is_stop = Column(Boolean, default=False)   # Stop-list

    category = relationship("Category", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    alice_order_id = Column(String)     # Alice POS da yaratilgan ID
    yandex_claim_id = Column(String)    # Yandex Delivery claim ID
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


class CourierStatus(enum.Enum):
    pending = "pending"      # Ro'yxatdan o'tgan, admin tasdiqlamagan
    active = "active"        # Faol kuryer
    blocked = "blocked"      # Bloklangan


class Courier(Base):
    __tablename__ = "couriers"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    transport_type = Column(String, default="car")  # car, bike, walk
    status = Column(Enum(CourierStatus), default=CourierStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="reviews")
