"""DB'dagi nozik field'larni shifrlash uchun helper (Fernet AES-128-CBC + HMAC).

Strategiya — backward-compat: yangi yozilgan qiymatlar shifrlangan ("enc:" prefiks)
saqlanadi; eski plaintext qiymatlar o'qishda avtomatik aniqlanadi va keyingi
write paytida shifrlanadi.

Kalit: FIELD_ENCRYPTION_KEY .env'dan olinadi (base64-urlsafe, 32 bayt).
Kalit yo'q bo'lsa, shifrlash o'chiriladi (DEV/test rejim) — production'da
.env'da bo'lishi shart.

Yangi kalit yaratish:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

_FERNET = None


def _get_fernet():
    """Lazy-load Fernet instance."""
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    key = (os.getenv("FIELD_ENCRYPTION_KEY") or "").strip()
    if not key:
        log.warning(
            "FIELD_ENCRYPTION_KEY .env'da o'rnatilmagan — nozik field'lar plaintext'da saqlanadi! "
            "Production'da bu xavfli. Kalit yaratish uchun: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
        _FERNET = False  # sentinel — keyingi safar urinmaslik uchun
        return None
    try:
        from cryptography.fernet import Fernet
        _FERNET = Fernet(key.encode())
        return _FERNET
    except Exception as e:
        log.error("FIELD_ENCRYPTION_KEY noto'g'ri formatda: %s", e)
        _FERNET = False
        return None


_PREFIX = "enc:"


def encrypt_field(plaintext: Optional[str]) -> Optional[str]:
    """Plain → shifrlangan ("enc:" prefiks bilan). Kalit yo'q bo'lsa plain qaytaradi."""
    if not plaintext:
        return plaintext
    if plaintext.startswith(_PREFIX):
        return plaintext  # allaqachon shifrlangan
    f = _get_fernet()
    if not f:
        return plaintext
    try:
        token = f.encrypt(plaintext.encode()).decode()
        return _PREFIX + token
    except Exception as e:
        log.error("encrypt_field xato: %s", e)
        return plaintext


def decrypt_field(stored: Optional[str]) -> Optional[str]:
    """Shifrlangan ("enc:..." formatda) → plain. Eski plaintext bo'lsa o'zini qaytaradi."""
    if not stored:
        return stored
    if not stored.startswith(_PREFIX):
        return stored  # legacy plaintext
    f = _get_fernet()
    if not f:
        # Kalit yo'q yoki noto'g'ri — token deshifrlanmaydi
        log.warning("Shifrlangan field bor lekin FIELD_ENCRYPTION_KEY yo'q")
        return None
    try:
        return f.decrypt(stored[len(_PREFIX):].encode()).decode()
    except Exception as e:
        log.error("decrypt_field xato (kalit o'zgartirilgan?): %s", e)
        return None


def mask_secret(value: Optional[str], visible: int = 6) -> str:
    """Log uchun: faqat birinchi N belgi + *** ko'rsatish."""
    if not value:
        return "<empty>"
    plain = decrypt_field(value) or value
    if len(plain) <= visible:
        return "***"
    return f"{plain[:visible]}***"
