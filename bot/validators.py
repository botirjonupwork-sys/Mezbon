"""Bot uchun umumiy validatsiya yordamchilari."""
from __future__ import annotations

import re

_DIGITS = re.compile(r"\D+")


def normalize_uz_phone(raw: str | None) -> str | None:
    """O'zbekiston telefon raqamini tekshirib, +998XXXXXXXXX ko'rinishiga keltiradi.

    Qabul qilinadigan kiritmalar (bo'sh joy/qavs/chiziqcha e'tiborsiz):
      +998 90 123 45 67 → +998901234567
      998901234567       → +998901234567
      901234567 (9 raqam, operator kodi bilan) → +998901234567
    To'liq/yaroqsiz bo'lmasa None qaytaradi (jami operator+raqam = 9 ta).
    """
    if not raw:
        return None
    digits = _DIGITS.sub("", str(raw))
    # 998 prefiksini olib tashlaymiz
    if digits.startswith("998"):
        digits = digits[3:]
    elif digits.startswith("0") and len(digits) == 10:
        # 0 bilan boshlangan 10 xonali (mahalliy yozuv) — 0 ni olib tashlaymiz
        digits = digits[1:]
    if len(digits) != 9 or not digits.isdigit():
        return None
    # O'zbek mobil operator kodlari 2-xonali, 1-raqam odatda 9/8/7/3/etc — qattiq
    # cheklamaymiz, faqat 9 xonali bo'lishini talab qilamiz.
    return "+998" + digits
