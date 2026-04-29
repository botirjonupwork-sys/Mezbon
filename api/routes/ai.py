"""AI Call Operator REST endpoints.

Vapi/Retell yoki o'z SIP gateway'imiz transcribed user message'ni shu yerga
yuboradi. Biz LLM (OpenAI function calling) orqali javob va kerakli
action'larni qaytaramiz. Buyurtma tasdiqlansa — ichki `Order` yaratiladi
va catering bo'lsa, mijoz catering kanaliga yo'naltiriladi.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_deps import require_plan_feature
from api.database import get_db
from api.routes.users import get_or_create_phone_user
from api.services import ai_agent
from database.models import (
    DeliveryType, Order, OrderItem, OrderStatus, Restaurant,
)


router = APIRouter(prefix="/ai", tags=["ai"])


# ── Schemas ──────────────────────────────────────────────────────────────

class ProcessCallRequest(BaseModel):
    call_id: str = Field(..., description="Ovozli provider tomonidan beriladigan unikal call ID")
    user_phone: str = Field(..., description="+998XXXXXXXXX formatida")
    message: str = Field(..., description="Foydalanuvchi gapining transcript matni")
    user_name: Optional[str] = None
    end_call: bool = False  # True bo'lsa sessiyani yopamiz


class ProcessCallResponse(BaseModel):
    reply: str
    actions: list[dict]
    cart: list[dict]
    address: Optional[str] = None
    confirmed: bool = False
    transferred: bool = False
    order_id: Optional[int] = None
    is_catering: bool = False


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/process-call", response_model=ProcessCallResponse)
async def process_call(
    body: ProcessCallRequest,
    restaurant_id: int = Depends(require_plan_feature("ai_agent")),
    db: AsyncSession = Depends(get_db),
):
    """Bitta turn — foydalanuvchi reploki uchun AI javob.

    Buyurtma tasdiqlansa (`confirmed=True`) ichki Order yaratamiz va
    `actions` ichida `{"type":"create_order","order_id":N}` qaytaramiz.
    Catering bo'lsa `transferred=True` va `actions=[{"type":"transfer_to_catering"}]`.
    """
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak (super admin uchun ham)")

    rest_res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    restaurant = rest_res.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(404, "Restoran topilmadi")

    if not restaurant.ai_agent_enabled:
        raise HTTPException(403, "AI Operator restoran sozlamalarida o'chirilgan")

    # Sessiya
    sess = ai_agent.get_session(body.call_id, restaurant.id, body.user_phone)

    # AI javobini olish
    result = await ai_agent.process_message(db, restaurant, sess, body.message)

    actions: list[dict] = []
    order_id: Optional[int] = None

    # Catering yoki transfer
    if result.get("transferred") or (result.get("is_catering") and result.get("confirmed")):
        actions.append({
            "type": "transfer_to_catering",
            "phone": body.user_phone,
            "cart": result.get("cart", []),
            "address": result.get("address"),
        })
        ai_agent.end_session(body.call_id)
        return ProcessCallResponse(
            reply=result["reply"], actions=actions, cart=result.get("cart", []),
            address=result.get("address"), confirmed=False, transferred=True,
            is_catering=bool(result.get("is_catering")),
        )

    # Tasdiqlangan oddiy buyurtma
    if result.get("confirmed") and result.get("cart"):
        try:
            order_id = await _create_ai_order(
                db=db, restaurant_id=restaurant.id,
                phone=body.user_phone, user_name=body.user_name,
                cart=result["cart"], address=result.get("address"),
            )
            actions.append({"type": "create_order", "order_id": order_id})
        except Exception as e:
            actions.append({"type": "error", "message": f"Order yaratishda xato: {e}"})
        ai_agent.end_session(body.call_id)

    if body.end_call:
        ai_agent.end_session(body.call_id)

    return ProcessCallResponse(
        reply=result["reply"],
        actions=actions,
        cart=result.get("cart", []),
        address=result.get("address"),
        confirmed=bool(result.get("confirmed")),
        transferred=False,
        order_id=order_id,
        is_catering=bool(result.get("is_catering")),
    )


@router.post("/end-call")
async def end_call(
    call_id: str,
    restaurant_id: int = Depends(require_plan_feature("ai_agent")),
):
    """Sessiyani yopish (provider call hangup hodisasida)."""
    ai_agent.end_session(call_id)
    return {"ok": True}


# ── Helpers ──────────────────────────────────────────────────────────────

async def _create_ai_order(
    db: AsyncSession,
    restaurant_id: int,
    phone: str,
    user_name: Optional[str],
    cart: list[dict],
    address: Optional[str],
) -> int:
    """Tasdiqlangan AI savatdan ichki Order yaratadi.

    AI orqali kelgan mijoz `phone:+998...` telegram_id bilan saqlanadi.
    Yetkazib berish/olib ketish: address bo'lsa delivery, aks holda pickup.
    """
    user = await get_or_create_phone_user(db, phone=phone, full_name=user_name)

    total = sum(float(i["price"]) * int(i["quantity"]) for i in cart)
    delivery_type = DeliveryType.delivery if address else DeliveryType.pickup

    order = Order(
        user_id=user.id,
        restaurant_id=restaurant_id,
        delivery_type=delivery_type,
        address=address,
        total_price=total,
        delivery_fee=0.0,
        status=OrderStatus.pending,
        order_kind="regular",
    )
    db.add(order)
    await db.flush()

    for item in cart:
        db.add(OrderItem(
            order_id=order.id,
            product_id=int(item["product_id"]),
            quantity=int(item["quantity"]),
            price=float(item["price"]),
        ))

    await db.commit()
    return order.id
