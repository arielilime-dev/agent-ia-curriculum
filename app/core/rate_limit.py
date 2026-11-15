"""In-memory sliding-window rate limiter.

It is intentionally small and dependency free: a single process keeps a deque
of timestamps per key.  For multi-instance deployments the same interface can
be backed by Redis without touching the API layer.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowRateLimiter:
    """Allow at most *limit* events per *window_seconds* for a given key."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> tuple[bool, int]:
        """Register an attempt for *key*.

        Returns ``(allowed, retry_after_seconds)``.  ``retry_after`` is 0 when
        the attempt is allowed and otherwise at least 1 second.
        """
        async with self._lock:
            now = self._clock()
            bucket = self._events.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                wait = self.window_seconds - (now - bucket[0])
                return False, max(1, int(wait + 0.999))
            bucket.append(now)
            return True, 0

    async def reset(self, key: str | None = None) -> None:
        """Clear counters for *key*, or everything when omitted."""
        async with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)
