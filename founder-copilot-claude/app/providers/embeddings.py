import hashlib
import re
from abc import ABC, abstractmethod

from app.config import settings
from app.utils.cache import LruTtlCache

class EmbeddingsProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]

    @property
    def provider_id(self) -> str:
        return self.__class__.__name__.lower()

    @property
    def model_name(self) -> str:
        return "unknown"


class LocalHashEmbeddingsProvider(EmbeddingsProvider):
    """Deterministic local embedding for demo portability."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self._provider_id = "hash"
        self._model_name = f"local_hash_{dim}"

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

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model_name(self) -> str:
        return self._model_name


class OpenAIEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, api_key: str, model: str, dim: int) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._dim = dim
        self._provider_id = "openai"

    def embed_text(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=text, dimensions=self._dim)
        return list(resp.data[0].embedding)

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model_name(self) -> str:
        return self._model


class GeminiEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._provider_id = "gemini"

    def embed_text(self, text: str) -> list[float]:
        result = self._client.models.embed_content(model=self._model, contents=text)
        emb = result.embeddings[0]
        vals = getattr(emb, "values", None) or getattr(emb, "embedding", None) or []
        return [float(x) for x in list(vals)]

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model_name(self) -> str:
        return self._model


class LocalSentenceTransformerEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, model_name: str, dim: int) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._dim = dim
        self._provider_id = "local"
        self._model_name = model_name

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

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model_name(self) -> str:
        return self._model_name


class CachedEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, inner: EmbeddingsProvider, ttl_seconds: int, max_size: int) -> None:
        self._inner = inner
        self._cache = LruTtlCache[list[float]](max_size=max_size, ttl_seconds=ttl_seconds)

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

    @property
    def provider_id(self) -> str:
        return self._inner.provider_id

    @property
    def model_name(self) -> str:
        return self._inner.model_name


def embedding_provider_identity(provider: EmbeddingsProvider) -> str:
    return f"{provider.provider_id}:{provider.model_name}"


def build_embeddings_provider() -> EmbeddingsProvider:
    provider = settings.embedding_provider.lower()
    vector_dim = settings.vector_dim

    if provider == "openai":
        key = settings.openai_api_key
        if not key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        model = settings.openai_embedding_model
        base: EmbeddingsProvider = OpenAIEmbeddingsProvider(key, model, vector_dim)
    elif provider == "gemini":
        key = settings.gemini_api_key
        if not key:
            raise ValueError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini")
        model = settings.gemini_embedding_model
        base = GeminiEmbeddingsProvider(key, model)
    elif provider == "local":
        model_name = settings.local_embedding_model
        base = LocalSentenceTransformerEmbeddingsProvider(model_name=model_name, dim=vector_dim)
    elif provider == "hash":
        base = LocalHashEmbeddingsProvider(dim=vector_dim)
    else:
        raise ValueError("EMBEDDING_PROVIDER must be one of: openai, gemini, local, hash")

    ttl = settings.embedding_cache_ttl_seconds
    size = settings.embedding_cache_max_size
    return CachedEmbeddingsProvider(inner=base, ttl_seconds=ttl, max_size=size)
