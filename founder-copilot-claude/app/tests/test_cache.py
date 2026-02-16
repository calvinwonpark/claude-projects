from app.utils.cache import LruTtlCache


def test_lru_eviction_keeps_recently_used_item():
    cache = LruTtlCache[int](max_size=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1  # mark a as most recently used
    cache.set("c", 3)  # should evict b
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3
    assert cache.stats.evictions == 1


def test_ttl_expiration_increments_stats():
    cache = LruTtlCache[int](max_size=2, ttl_seconds=60)
    cache.set("k", 9)
    cache._store["k"].expires_at = 0.0  # force expiration for deterministic test
    assert cache.get("k") is None
    assert cache.stats.expirations == 1
