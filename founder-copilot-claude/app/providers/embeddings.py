import hashlib
import os
import re
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheItem:
    value: list[float]
    expires_at: float


class LruTtlCache:
    def __init__(self, max_size: int, ttl_seconds: int) -> None:
        self.max_size = max(1, max_size)
        self.ttl_seconds = max(1, ttl_seconds)
        self._store: OrderedDict[str, CacheItem] = OrderedDict()

    def _now(self) -> float:
        import time

        return time.time()

    def get(self, key: str) -> list[float] | None:
        item = self._store.get(key)
        if not item:
            return None
        if item.expires_at <= self._now():
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return item.value

    def set(self, key: str, value: list[float]) -> None:
        self._store[key] = CacheItem(value=value, expires_at=self._now() + self.ttl_seconds)
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)


class EmbeddingsProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


class LocalHashEmbeddingsProvider(EmbeddingsProvider):
    """Deterministic local embedding for demo portability."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed_text(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        terms = re.findall(r"[a-zA-Z0-9_]+", (text or "").lower())
        for term in terms:
            digest = hashlib.sha256(term.encode("utf-8")).hexdigest()
            idx = int(digest[:8], 16) % self.dim
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OpenAIEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, api_key: str, model: str, dim: int) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._dim = dim

    def embed_text(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=text, dimensions=self._dim)
        return list(resp.data[0].embedding)


class GeminiEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def embed_text(self, text: str) -> list[float]:
        result = self._client.models.embed_content(model=self._model, contents=text)
        emb = result.embeddings[0]
        vals = getattr(emb, "values", None) or getattr(emb, "embedding", None) or []
        return [float(x) for x in list(vals)]


class LocalSentenceTransformerEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, model_name: str, dim: int) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._dim = dim

    def _norm_dim(self, vec: list[float]) -> list[float]:
        if len(vec) == self._dim:
            return vec
        if len(vec) > self._dim:
            return vec[: self._dim]
        return vec + [0.0] * (self._dim - len(vec))

    def embed_text(self, text: str) -> list[float]:
        vec = self._model.encode(text).tolist()
        return self._norm_dim([float(v) for v in vec])

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts).tolist()
        return [self._norm_dim([float(v) for v in vec]) for vec in vectors]


class CachedEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, inner: EmbeddingsProvider, ttl_seconds: int, max_size: int) -> None:
        self._inner = inner
        self._cache = LruTtlCache(max_size=max_size, ttl_seconds=ttl_seconds)

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(" ".join((text or "").lower().split()).encode("utf-8")).hexdigest()

    def embed_text(self, text: str) -> list[float]:
        key = self._key(text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        vec = self._inner.embed_text(text)
        self._cache.set(key, vec)
        return vec

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


def build_embeddings_provider() -> EmbeddingsProvider:
    provider = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    vector_dim = int(os.getenv("VECTOR_DIM", "1536"))

    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        base: EmbeddingsProvider = OpenAIEmbeddingsProvider(key, model, vector_dim)
    elif provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise ValueError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini")
        model = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        base = GeminiEmbeddingsProvider(key, model)
    elif provider == "local":
        model_name = os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        base = LocalSentenceTransformerEmbeddingsProvider(model_name=model_name, dim=vector_dim)
    elif provider == "hash":
        base = LocalHashEmbeddingsProvider(dim=vector_dim)
    else:
        raise ValueError("EMBEDDING_PROVIDER must be one of: openai, gemini, local, hash")

    ttl = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", "86400"))
    size = int(os.getenv("EMBEDDING_CACHE_MAX_SIZE", "5000"))
    return CachedEmbeddingsProvider(inner=base, ttl_seconds=ttl, max_size=size)
