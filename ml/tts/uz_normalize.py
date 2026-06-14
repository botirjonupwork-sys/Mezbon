"""O'zbek TTS matn normalizatori — raqam/narx/vaqt/sanani o'qiladigan so'zga.

Bu — TTS sifatining ENG MUHIM qismi (model emas). "12 500 so'm" ni
"o'n ikki ming besh yuz so'm" qilib bermasa, har qanday model yomon eshitiladi.
GPU shart emas — sof qoidalar. Aisha bilan ham, o'z modelimiz bilan ham ishlaydi.

Foydalanish:
  from ml.tts.uz_normalize import normalize_for_tts
  normalize_for_tts("Buyurtma 12500 so'm, soat 18:30 ga tayyor")
  → "Buyurtma o'n ikki ming besh yuz so'm, soat o'n sakkiz o'ttiz ga tayyor"
"""
from __future__ import annotations

import re

_UNITS = ["", "bir", "ikki", "uch", "toʻrt", "besh", "olti", "yetti", "sakkiz", "toʻqqiz"]
_TENS = ["", "oʻn", "yigirma", "oʻttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "toʻqson"]
_SCALES = [(10**9, "milliard"), (10**6, "million"), (10**3, "ming")]


def _below_1000(n: int) -> str:
    """1–999 → so'z."""
    parts = []
    h, rest = divmod(n, 100)
    if h:
        parts.append("yuz" if h == 1 else f"{_UNITS[h]} yuz")
    t, u = divmod(rest, 10)
    if t:
        parts.append(_TENS[t])
    if u:
        parts.append(_UNITS[u])
    return " ".join(parts)


def number_to_words(n: int) -> str:
    """Butun sonni o'zbekcha so'zga (0 .. milliardlar)."""
    if n == 0:
        return "nol"
    if n < 0:
        return "minus " + number_to_words(-n)
    parts = []
    for value, name in _SCALES:
        if n >= value:
            group, n = divmod(n, value)
            if group == 1 and name == "ming":
                parts.append("ming")           # 1000 = "ming" (bir-siz)
            else:
                parts.append(f"{number_to_words(group)} {name}")
    if n:
        parts.append(_below_1000(n))
    return " ".join(parts)


def _say_time(m: re.Match) -> str:
    h, mi = int(m.group(1)), int(m.group(2))
    if mi == 0:
        return number_to_words(h)
    mm = f"nol {number_to_words(mi)}" if mi < 10 else number_to_words(mi)
    return f"{number_to_words(h)} {mm}"


def _say_money(m: re.Match) -> str:
    digits = re.sub(r"\s", "", m.group(1))
    return f"{number_to_words(int(digits))} soʻm"


def _say_plain_number(m: re.Match) -> str:
    digits = m.group(0)
    if len(digits) > 9:   # telefon kabi — raqamma-raqam
        return " ".join(number_to_words(int(d)) for d in digits)
    return number_to_words(int(digits))


def normalize_for_tts(text: str) -> str:
    """Matnni TTS uchun tayyorlash — raqam/narx/vaqtni so'zga aylantirish."""
    if not text:
        return ""
    # 1) Vaqt HH:MM ("soat" qo'shilmaydi — matnda ko'pincha bor)
    text = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", _say_time, text)
    # 2) Narx — raqamdan boshlanadi (oldingi so'z bo'shlig'ini yemaydi)
    text = re.sub(r"(\d[\d\s]*\d|\d)\s*so[ʻ'`]?m\b", _say_money, text, flags=re.IGNORECASE)
    # 3) Foiz
    text = re.sub(r"(\d+)\s*%", lambda m: f"{number_to_words(int(m.group(1)))} foiz", text)
    # 4) Qolgan oddiy raqamlar (bo'shliq bo'ylab birlashtirmaymiz)
    text = re.sub(r"\d+", _say_plain_number, text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


if __name__ == "__main__":
    tests = [
        "Buyurtma 12500 so'm",
        "Soat 18:30 ga tayyor",
        "5 ta somsa, 60 000 so'm",
        "Chegirma 15%",
        "Telefon: 998901234567",
        "Soat 9:05 da",
        "1000 so'm",
        "2000000 so'm",
        "21 ta",
    ]
    for t in tests:
        print(f"{t!r}\n  → {normalize_for_tts(t)!r}\n")
