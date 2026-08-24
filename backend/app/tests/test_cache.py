"""Tests for the TTL cache."""

from __future__ import annotations

import asyncio
import time

from app.services.cache import TTLCache


async def test_cache_returns_cached_value():
    cache = TTLCache[int](ttl_seconds=60)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return 42

    a = await cache.get_or_set("k", factory)
    b = await cache.get_or_set("k", factory)
    assert a == b == 42
    assert calls["n"] == 1


async def test_cache_expires():
    cache = TTLCache[int](ttl_seconds=0.05)

    async def factory():
        return time.time_ns()

    a = await cache.get_or_set("k", factory)
    await asyncio.sleep(0.1)
    b = await cache.get_or_set("k", factory)
    assert a != b


async def test_cache_coalesces_concurrent_misses():
    """Multiple awaiters for the same key should produce only one factory call."""
    cache = TTLCache[int](ttl_seconds=60)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return 7

    results = await asyncio.gather(
        *[cache.get_or_set("k", factory) for _ in range(10)]
    )
    assert all(r == 7 for r in results)
    assert calls["n"] == 1


async def test_cache_invalidate():
    cache = TTLCache[int](ttl_seconds=60)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return calls["n"]

    assert await cache.get_or_set("k", factory) == 1
    cache.invalidate("k")
    assert await cache.get_or_set("k", factory) == 2


async def test_cache_stores_none_as_a_real_value():
    """A negative upstream result is cached, not re-fetched every call."""
    cache = TTLCache[int | None](ttl_seconds=60)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return None

    assert await cache.get_or_set("k", factory) is None
    assert await cache.get_or_set("k", factory) is None
    assert calls["n"] == 1


async def test_cache_evicts_least_recently_used_beyond_maxsize():
    cache = TTLCache[int](ttl_seconds=60, maxsize=2)

    async def factory_for(value: int):
        async def factory():
            return value

        return factory

    await cache.get_or_set("a", await factory_for(1))
    await cache.get_or_set("b", await factory_for(2))
    # Touch "a" so "b" becomes the least recently used entry.
    await cache.get_or_set("a", await factory_for(99))
    await cache.get_or_set("c", await factory_for(3))

    assert len(cache._data) == 2
    assert set(cache._data) == {"a", "c"}


async def test_cache_does_not_leak_locks_across_distinct_keys():
    """The key space is caller-supplied, so locks must not accumulate."""
    cache = TTLCache[int](ttl_seconds=60, maxsize=8)

    async def factory():
        return 1

    for i in range(100):
        await cache.get_or_set(f"ticker-{i}", factory)

    assert cache._locks == {}
    assert len(cache._data) <= 8


async def test_cache_releases_lock_when_factory_raises():
    cache = TTLCache[int](ttl_seconds=60)

    async def boom():
        raise RuntimeError("upstream down")

    for _ in range(5):
        try:
            await cache.get_or_set("k", boom)
        except RuntimeError:
            pass

    assert cache._locks == {}
    # A failed factory caches nothing, so the next success is still fetched.
    async def factory():
        return 5

    assert await cache.get_or_set("k", factory) == 5
