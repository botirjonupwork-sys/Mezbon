"""Bot util funksiyalari."""
from aiogram.fsm.context import FSMContext


# State clear qilganda saqlanishi kerak bo'lgan kalitlar
_PRESERVED_KEYS = ("branch_id", "branch_name", "user_lat", "user_lon")


async def clear_state_preserve_branch(state: FSMContext) -> None:
    """FSM state'ni tozalab, lekin filial ma'lumotini saqlab qolish."""
    data = await state.get_data()
    preserved = {k: data[k] for k in _PRESERVED_KEYS if k in data and data[k] is not None}
    await state.clear()
    if preserved:
        await state.update_data(**preserved)
