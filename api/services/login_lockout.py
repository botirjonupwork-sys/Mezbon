"""Username asosida login lockout — bruteforce'dan himoya.

Per-IP rate limit (SlowAPI) qo'shimcha — botnetdan distributed bruteforce'ni
to'sish uchun aynan username bo'yicha lockout kerak.

Strategiya:
  - Har username uchun fail counter va lockout deadline saqlanadi
  - 5 ta ketma-ket xato → 15 daqiqa lockout
  - Muvaffaqiyatli login → counter tozalanadi

In-memory (process-bo'yicha). Multi-process deploy uchun Redis kerak — TODO.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _AttemptInfo:
    failures: int = 0
    locked_until: float = 0.0


class LoginLockout:
    """Threadsafe lockout tracker."""

    def __init__(self, max_failures: int = 5, lockout_seconds: int = 900,
                 fail_window_seconds: int = 1800):
        self._max = max_failures
        self._lockout = lockout_seconds
        self._window = fail_window_seconds
        self._lock = threading.Lock()
        self._data: dict[str, _AttemptInfo] = {}
        self._first_fail: dict[str, float] = {}  # username → first fail time

    def is_locked(self, username: str) -> tuple[bool, int]:
        """Username qulflangan bo'lsa True va qolgan sekund qaytaradi."""
        if not username:
            return False, 0
        with self._lock:
            info = self._data.get(username)
            if not info:
                return False, 0
            now = time.time()
            if info.locked_until > now:
                return True, int(info.locked_until - now)
            return False, 0

    def record_failure(self, username: str) -> tuple[int, int]:
        """Xato yozadi. Qaytaradi: (joriy fail soni, lockout sekundi yoki 0)."""
        if not username:
            return 0, 0
        with self._lock:
            now = time.time()
            info = self._data.setdefault(username, _AttemptInfo())

            # Fail oynasini reset qilish (oxirgi xatodan oraliq vaqt o'tgan bo'lsa)
            first_fail = self._first_fail.get(username, 0)
            if first_fail and (now - first_fail) > self._window:
                info.failures = 0
                self._first_fail[username] = now
            elif not first_fail:
                self._first_fail[username] = now

            info.failures += 1
            if info.failures >= self._max:
                info.locked_until = now + self._lockout
                return info.failures, self._lockout
            return info.failures, 0

    def record_success(self, username: str) -> None:
        """Muvaffaqiyatli login — counter va lockout tozalanadi."""
        if not username:
            return
        with self._lock:
            self._data.pop(username, None)
            self._first_fail.pop(username, None)


# Global instance
login_lockout = LoginLockout(max_failures=5, lockout_seconds=900, fail_window_seconds=1800)
