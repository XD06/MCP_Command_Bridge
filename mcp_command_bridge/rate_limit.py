from __future__ import annotations

import time
from threading import Lock


class RateLimiter:
    """Thread-safe sliding-window rate limiter (per-minute, in-memory)."""

    def __init__(self, per_minute: int) -> None:
        self._per_minute = per_minute
        self._buckets: dict[str, list[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        if self._per_minute <= 0:
            return True
        now = time.monotonic()
        cutoff = now - 60.0
        with self._lock:
            bucket = self._buckets.get(key, [])
            bucket = [t for t in bucket if t > cutoff]
            if len(bucket) >= self._per_minute:
                self._buckets[key] = bucket
                return False
            bucket.append(now)
            self._buckets[key] = bucket
            return True

    def remaining(self, key: str) -> int:
        """Return how many requests remain in the current window for *key*."""
        if self._per_minute <= 0:
            return -1
        now = time.monotonic()
        cutoff = now - 60.0
        with self._lock:
            bucket = [t for t in self._buckets.get(key, []) if t > cutoff]
            self._buckets[key] = bucket
            return max(0, self._per_minute - len(bucket))
