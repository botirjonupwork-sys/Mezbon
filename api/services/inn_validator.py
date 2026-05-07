"""O'zbekiston Respublikasi INN/STIR validatori.

INN (Identifikatsiya Nomeri Nalogoplatel'shika) yoki STIR (Soliq To'lovchining
Identifikatsion Raqami) — yuridik shaxslar uchun **9 xonali** raqam.

Standart manba: O'zR Davlat soliq qo'mitasi (https://my.soliq.uz)

Eslatma: jismoniy shaxslar uchun **PINFL — 14 xonali** raqam ishlatiladi, lekin
biz restoran-platformamizda faqat yuridik shaxslar bilan ishlaymiz.

Validatsiya darajalari:
1. **Format** — 9 ta raqam, faqat 0-9 (mahalliy tekshiruv, real-time)
2. **Checksum** — algoritm asosida (placeholder: hozircha skip; real algoritm
   nashr etilmagan — yuridik shaxs INN'ida formal checksum yo'q deb hisoblanadi)
3. **Soliq API tekshiruv** — `/api.soliq.uz/inn-check` (alohida xizmat sifatida,
   `verify_inn_with_soliq()` placeholder qoldirilgan, kelajakda real ulanadi)

Foydalanish:
    from api.services.inn_validator import validate_inn_format, InvalidINNError

    try:
        clean_inn = validate_inn_format("123456789")  # str qaytaradi
    except InvalidINNError as e:
        raise HTTPException(400, str(e))
"""
from __future__ import annotations

import re

# 9 xonali, faqat raqamlar
_INN_RE = re.compile(r"^\d{9}$")

# Aniq noto'g'ri INN'lar (test/spam'lar)
_BLACKLIST_INN = {
    "000000000",
    "111111111",
    "123456789",   # ko'p test/spam'larda uchraydi
}


class InvalidINNError(ValueError):
    """INN format yoki checksum yaroqsiz."""
    pass


def validate_inn_format(inn: str | None) -> str:
    """INN formatini tekshiradi va tozalangan (faqat raqamlar) shaklini qaytaradi.

    Raises:
        InvalidINNError — agar format noto'g'ri bo'lsa

    Misollar:
        validate_inn_format("123 456 789")  → "123456789"
        validate_inn_format("12345")        → InvalidINNError
        validate_inn_format("ABC123456")    → InvalidINNError
    """
    if not inn:
        raise InvalidINNError("INN bo'sh bo'lmasligi kerak")

    # Probel, defis va boshqa belgilarni olib tashlash
    cleaned = re.sub(r"[\s\-_]", "", str(inn).strip())

    if not _INN_RE.match(cleaned):
        raise InvalidINNError(
            f"INN 9 ta raqamdan iborat bo'lishi kerak (kiritilgan: {len(cleaned)} ta belgi)"
        )

    if cleaned in _BLACKLIST_INN:
        raise InvalidINNError("Bu INN test/yaroqsiz qiymat")

    if cleaned == cleaned[0] * 9:    # "555555555" kabi
        raise InvalidINNError("INN bir xil raqamlardan iborat bo'lmasligi kerak")

    return cleaned


def inn_checksum_valid(inn: str) -> bool:
    """INN checksum tekshiruvi (placeholder).

    O'zR yuridik shaxs INN'ida ochiq checksum algoritmi nashr etilmagan.
    Real tekshiruv uchun `verify_inn_with_soliq()` (Soliq API) ishlatilishi kerak.

    Hozircha format to'g'ri bo'lsa True qaytaradi (no-op).
    """
    return _INN_RE.match(inn or "") is not None


async def verify_inn_with_soliq(inn: str) -> dict:
    """O'zR Soliq qo'mitasi API orqali INN tekshiruv.

    Soliq qo'mitasining ochiq API'lari:
      - https://api.soliq.uz/inn-info (rasmiy, API kalit kerak)
      - https://my.soliq.uz/api/services/get/get_company (cookie-based)
      - https://api.didox.uz/api/v1/companies/inn/{inn} (3rd-party, ishonchli mirror)

    Tartib:
      1. Format tekshiruvi (mahalliy)
      2. SOLIQ_API_KEY env bo'lsa — rasmiy API
      3. Aks holda — Didox public mirror (kalit kerak emas)
      4. Hech qaysi javob bermasa — format-only natija
    """
    import os
    import httpx

    try:
        clean = validate_inn_format(inn)
    except InvalidINNError as e:
        return {"valid": False, "error": str(e)}

    soliq_key = (os.getenv("SOLIQ_API_KEY") or "").strip()

    # 1) Soliq rasmiy API (kalit bo'lsa)
    if soliq_key:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(
                    f"https://api.soliq.uz/inn-info/{clean}",
                    headers={"Authorization": f"Bearer {soliq_key}"},
                )
            if 200 <= r.status_code < 300:
                d = r.json() or {}
                return {
                    "valid": True,
                    "inn": clean,
                    "name": d.get("name") or d.get("organization_name"),
                    "type": d.get("type") or d.get("legal_form"),
                    "registered_at": d.get("registered_at") or d.get("registration_date"),
                    "_source": "soliq_api",
                }
        except Exception:
            pass

    # 2) Didox public mirror (kalit kerak emas)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"https://api.didox.uz/api/v1/companies/inn/{clean}")
        if 200 <= r.status_code < 300:
            d = r.json() or {}
            if d.get("name") or d.get("companyName"):
                return {
                    "valid": True,
                    "inn": clean,
                    "name": d.get("name") or d.get("companyName"),
                    "type": d.get("type") or d.get("orgForm"),
                    "registered_at": d.get("registeredAt") or d.get("registrationDate"),
                    "_source": "didox_mirror",
                }
    except Exception:
        pass

    # 3) Format-only fallback
    return {
        "valid": True,
        "inn": clean,
        "name": None,
        "type": None,
        "registered_at": None,
        "_source": "format_only",
    }
