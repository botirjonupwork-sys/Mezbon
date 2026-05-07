"""Webhook latency va success-rate metrikalari (Faza 7).

In-memory ring buffer — har webhook so'rov uchun:
    - duration_ms
    - status_code
    - timestamp

Production'da bu Redis/Prometheus'ga ko'chiriladi. Hozircha process-local
(uvicorn worker bo'yicha alohida).

Dashboard endpoint: `/super-admin/monitoring/webhooks`
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


# Har endpoint uchun oxirgi 1000 ta so'rov saqlanadi
RING_SIZE = 1000

_buffers: dict[str, deque] = {
    "click": deque(maxlen=RING_SIZE),
    "payme": deque(maxlen=RING_SIZE),
    "telegram_prepare": deque(maxlen=RING_SIZE),
    "telegram_precheck": deque(maxlen=RING_SIZE),
    "telegram_confirm": deque(maxlen=RING_SIZE),
}


@dataclass
class WebhookSample:
    timestamp: float          # Unix epoch
    duration_ms: float
    status_code: int
    path: str
    error: Optional[str] = None


def record(endpoint_key: str, duration_ms: float, status_code: int,
           path: str = "", error: Optional[str] = None) -> None:
    """Yangi webhook sample qo'shish (thread-safe deque)."""
    buf = _buffers.get(endpoint_key)
    if buf is None:
        buf = deque(maxlen=RING_SIZE)
        _buffers[endpoint_key] = buf
    buf.append(WebhookSample(
        timestamp=time.time(),
        duration_ms=duration_ms,
        status_code=status_code,
        path=path,
        error=error,
    ))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def get_stats(endpoint_key: str, window_seconds: int = 3600) -> dict:
    """Oxirgi N soniyadagi statistika (default: 1 soat)."""
    buf = _buffers.get(endpoint_key)
    if not buf:
        return {"endpoint": endpoint_key, "samples": 0}

    cutoff = time.time() - window_seconds
    recent = [s for s in buf if s.timestamp >= cutoff]
    if not recent:
        return {"endpoint": endpoint_key, "samples": 0, "window_seconds": window_seconds}

    durations = [s.duration_ms for s in recent]
    success = sum(1 for s in recent if 200 <= s.status_code < 400)
    fail = len(recent) - success

    return {
        "endpoint": endpoint_key,
        "window_seconds": window_seconds,
        "samples": len(recent),
        "success": success,
        "failed": fail,
        "success_rate_pct": round(success / len(recent) * 100, 2),
        "p50_ms": round(percentile(durations, 50), 2),
        "p95_ms": round(percentile(durations, 95), 2),
        "p99_ms": round(percentile(durations, 99), 2),
        "max_ms": round(max(durations), 2),
        "min_ms": round(min(durations), 2),
    }


def get_all_stats(window_seconds: int = 3600) -> list[dict]:
    return [get_stats(k, window_seconds) for k in _buffers.keys()]


def detect_anomalies(window_seconds: int = 3600,
                     min_samples: int = 10,
                     fail_threshold_pct: float = 5.0,
                     latency_threshold_ms: float = 5000.0) -> list[dict]:
    """Anomaliyalarni topish — yuqori failure rate yoki sekinlashish."""
    anomalies = []
    for key in _buffers.keys():
        s = get_stats(key, window_seconds)
        if s["samples"] < min_samples:
            continue
        if 100 - s.get("success_rate_pct", 100) > fail_threshold_pct:
            anomalies.append({
                "endpoint": key,
                "type": "high_failure_rate",
                "value_pct": round(100 - s["success_rate_pct"], 2),
                "threshold_pct": fail_threshold_pct,
                "samples": s["samples"],
            })
        if s.get("p95_ms", 0) > latency_threshold_ms:
            anomalies.append({
                "endpoint": key,
                "type": "high_latency",
                "p95_ms": s["p95_ms"],
                "threshold_ms": latency_threshold_ms,
                "samples": s["samples"],
            })
    return anomalies
