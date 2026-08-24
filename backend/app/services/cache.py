"""Tiny async-safe TTL cache.

Used to dampen repeat calls to yfinance, NewsAPI, and SEC during burst traffic
without pulling in Redis. Keys are arbitrary hashables; values are anything.

  - Per-key expiration
  - Concurrent fetches for the same key coalesce on a single `asyncio.Lock` so
    we don't issue N parallel upstream calls for a hot key (thundering herd).
  - Bounded: every cache here is keyed on a caller-supplied ticker, so the key
    space is effectively unbounded. Entries are capped at `maxsize` and evicted
    least-recently-used; the coalescing locks are reference-counted and dropped
    as soon as the last waiter leaves (including when the factory raises).
  - `None` is a cacheable value, distinguished from "absent" by a sentinel — a
    negative upstream result is exactly what we most want to stop re-fetching.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, cast

T = TypeVar("T")

DEFAULT_MAXSIZE = 256

# Distinguishes "no entry" from "entry whose value is None".
_MISS: Any = object()


@dataclass(slots=True)
class _KeyLock:
    """A coalescing lock plus the number of callers currently using it."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    waiters: int = 0


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float, maxsize: int = DEFAULT_MAXSIZE):
        self.ttl = ttl_seconds
        self.maxsize = max(1, maxsize)
        # Ordered most-recently-used last, so popitem(last=False) evicts the LRU.
        self._data: OrderedDict[Any, tuple[float, T]] = OrderedDict()
        self._locks: dict[Any, _KeyLock] = {}
        self._global_lock = asyncio.Lock()

    def _get_fresh(self, key: Any) -> Any:
        """Return the live value for `key`, or `_MISS` if absent or expired."""
        entry = self._data.get(key)
        if entry is None:
            return _MISS
        expires_at, value = entry
        # Monotonic: a wall-clock jump must not resurrect or expire entries.
        if expires_at <= time.monotonic():
            del self._data[key]
            return _MISS
        self._data.move_to_end(key)
        return value

    def _store(self, key: Any, value: T) -> None:
        self._data[key] = (time.monotonic() + self.ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    async def get_or_set(self, key: Any, factory: Callable[[], Awaitable[T]]) -> T:
        # Fast path: cached + fresh.
        hit = self._get_fresh(key)
        if hit is not _MISS:
            return cast(T, hit)

        # Slow path: acquire per-key lock to coalesce concurrent misses.
        async with self._global_lock:
            entry = self._locks.get(key)
            if entry is None:
                entry = _KeyLock()
                self._locks[key] = entry
            entry.waiters += 1

        try:
            async with entry.lock:
                hit = self._get_fresh(key)
                if hit is not _MISS:
                    return cast(T, hit)
                value = await factory()
                self._store(key, value)
                return value
        finally:
            # Runs on the factory's exception too, so a persistently failing
            # key cannot leak a lock per distinct ticker.
            async with self._global_lock:
                entry.waiters -= 1
                if entry.waiters <= 0:
                    self._locks.pop(key, None)

    def invalidate(self, key: Any) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()
        self._locks.clear()
