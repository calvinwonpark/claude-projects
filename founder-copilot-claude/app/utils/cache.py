from collections import OrderedDict
from dataclasses import dataclass
import time
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0


@dataclass
class _CacheItem(Generic[T]):
    value: T
    expires_at: float


class LruTtlCache(Generic[T]):
    def __init__(self, *, max_size: int, ttl_seconds: int) -> None:
        self.max_size = max(1, int(max_size))
        self.ttl_seconds = max(1, int(ttl_seconds))
        self._store: OrderedDict[str, _CacheItem[T]] = OrderedDict()
        self.stats = CacheStats()

    def _now(self) -> float:
        return time.time()

    def get(self, key: str) -> T | None:
        item = self._store.get(key)
        if item is None:
            self.stats.misses += 1
            return None
        if item.expires_at <= self._now():
            self._store.pop(key, None)
            self.stats.expirations += 1
            self.stats.misses += 1
            return None
        self._store.move_to_end(key)
        self.stats.hits += 1
        return item.value

    def set(self, key: str, value: T) -> None:
        self._store[key] = _CacheItem(value=value, expires_at=self._now() + self.ttl_seconds)
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)
            self.stats.evictions += 1

