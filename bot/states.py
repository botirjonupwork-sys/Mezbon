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
