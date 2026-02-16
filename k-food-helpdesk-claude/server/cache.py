import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheEntry(Generic[V]):
    value: V
    expires_at: float


class LruTtlCache(Generic[K, V]):
    """Small in-memory cache with LRU eviction and TTL expiration."""

    def __init__(self, max_size: int, ttl_seconds: int) -> None:
        self._max_size = max(1, max_size)
        self._ttl_seconds = max(1, ttl_seconds)
        self._store: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = Lock()
        self.hits = 0
        self.misses = 0

    def _is_valid(self, entry: CacheEntry[V]) -> bool:
        return entry.expires_at > time.time()

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                self.misses += 1
                return None
            if not self._is_valid(entry):
                self._store.pop(key, None)
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return entry.value

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._store[key] = CacheEntry(value=value, expires_at=time.time() + self._ttl_seconds)
            self._store.move_to_end(key)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            requests = self.hits + self.misses
            hit_rate = (self.hits / requests) if requests else 0.0
            return {"hits": self.hits, "misses": self.misses, "hit_rate": round(hit_rate, 4), "size": len(self._store)}
