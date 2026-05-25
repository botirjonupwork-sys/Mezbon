"""Webhook replay himoyasi uchun in-memory nonce cache.

Click/Payme webhook'larida (click_trans_id, action, sign_time) tuple TTL bilan
saqlanadi. Bir xil kortej takror kelsa → replay deb rad etiladi.

Cheklov: bu cache xotirada (process bo'yicha). Restart paytida tozalanadi —
shu vaqt oynasida replay bo'lishi mumkin. Multi-process deploy uchun Redis
yoki DB-backed cache kerak (TODO).
"""
from __future__ import annotations

import threading
import time
from typing import Tuple


class NonceCache:
    """Threadsafe LRU-ga o'xshash, TTL bilan."""

    def __init__(self, ttl_seconds: int = 600, max_size: int = 10000):
        self._ttl = ttl_seconds
        self._max = max_size
        self._lock = threading.Lock()
        self._data: dict[Tuple, float] = {}  # nonce → expiry timestamp

    def _gc(self) -> None:
        """Eskirgan yozuvlarni tozalash. Lock ostida chaqiriladi."""
        now = time.time()
        # Lazy GC: faqat agar cache to'la bo'lsa
        if len(self._data) >= self._max:
            for k, exp in list(self._data.items()):
                if exp < now:
                    del self._data[k]
            # Hali ham to'la bo'lsa eng eski elementlarni o'chiramiz
            if len(self._data) >= self._max:
                items = sorted(self._data.items(), key=lambda x: x[1])
                for k, _ in items[: len(self._data) - self._max + 100]:
                    del self._data[k]

    def check_and_record(self, nonce: Tuple) -> bool:
        """Nonce yangimi (True) yoki replaymi (False)?

        Yangi bo'lsa cache'ga yoziladi va True qaytaradi.
        """
        with self._lock:
            now = time.time()
            existing = self._data.get(nonce)
            if existing and existing > now:
                # Hali expiry'da — replay
                return False
            self._gc()
            self._data[nonce] = now + self._ttl
            return True


# Global cache — webhook handler'lari shu instance'dan foydalanadi.
click_nonce_cache = NonceCache(ttl_seconds=600, max_size=10000)
payme_nonce_cache = NonceCache(ttl_seconds=600, max_size=10000)
