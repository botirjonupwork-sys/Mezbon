from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    full_name = State()
    phone = State()


class OrderFlow(StatesGroup):
    choosing_delivery = State()
    entering_address = State()
    entering_comment = State()
    choosing_payment = State()
    confirming = State()


class ReviewFlow(StatesGroup):
    rating = State()
    comment = State()


class CateringFlow(StatesGroup):
    choosing_product = State()
    choosing_quantity = State()
    choosing_delivery = State()
    choosing_date = State()
    choosing_time = State()
    entering_phone = State()
    entering_location = State()
    choosing_payment_method = State()
    choosing_payment_timing = State()
    entering_comment = State()
    confirming = State()
