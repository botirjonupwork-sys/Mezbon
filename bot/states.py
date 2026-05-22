from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    full_name = State()
    phone = State()


class OrderFlow(StatesGroup):
    choosing_delivery = State()
    choosing_time = State()        # Faza 10: dastavka vaqti — Hozir / Keyinroq slot
    entering_address = State()
    entering_comment = State()
    choosing_payment = State()
    confirming = State()


class ReviewFlow(StatesGroup):
    rating = State()
    comment = State()


class CateringFlow(StatesGroup):
    choosing_group = State()         # Somsa / Non
    selecting_items = State()        # Har bir mahsulot uchun miqdor
    entering_quantity = State()      # Bitta mahsulot uchun miqdor kiritish
    choosing_delivery = State()
    choosing_date = State()
    entering_date_custom = State()   # Qo'lda sana kiritish
    choosing_time = State()
    entering_time_custom = State()
    entering_phone = State()
    entering_location = State()
    choosing_payment_method = State()
    choosing_payment_timing = State()
    entering_comment = State()
    confirming = State()
