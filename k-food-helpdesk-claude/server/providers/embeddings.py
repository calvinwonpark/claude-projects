import os
from abc import ABC, abstractmethod
from typing import List


class EmbeddingsProvider(ABC):
    """Embedding provider interface used by both server retrieval and indexer ingestion."""

    dimension: int

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        raise NotImplementedError

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(text) for text in texts]


class GeminiEmbeddingsProvider(EmbeddingsProvider):
    dimension = 768

    def __init__(self, api_key: str, model: str = "gemini-embedding-001") -> None:
        from google import genai

        self._model = model
        self._client = genai.Client(api_key=api_key)

    def embed_text(self, text: str) -> List[float]:
        result = self._client.models.embed_content(model=self._model, contents=text)
        embedding = list(result.embeddings[0].values)
        return embedding[: self.dimension]


class OpenAIEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, api_key: str, model: str, dimension: int = 768) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.dimension = dimension

    def embed_text(self, text: str) -> List[float]:
        response = self._client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self.dimension,
        )
        return list(response.data[0].embedding)


class LocalEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, model_name: str, dimension: int = 768) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dimension = dimension

    def _normalize_dim(self, vec: List[float]) -> List[float]:
        if len(vec) == self.dimension:
            return vec
        if len(vec) > self.dimension:
            return vec[: self.dimension]
        return vec + [0.0] * (self.dimension - len(vec))

    def embed_text(self, text: str) -> List[float]:
        vec = self._model.encode(text).tolist()
        return self._normalize_dim(vec)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        vectors = self._model.encode(texts).tolist()
        return [self._normalize_dim(list(v)) for v in vectors]


def build_embeddings_provider() -> EmbeddingsProvider:
    provider = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()
    embedding_dim = int(os.getenv("EMBEDDING_DIM", "768"))
    if embedding_dim != 768:
        raise ValueError("Current DB schema uses VECTOR(768); set EMBEDDING_DIM=768")

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini")
        return GeminiEmbeddingsProvider(api_key=api_key)

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        return OpenAIEmbeddingsProvider(api_key=api_key, model=model, dimension=embedding_dim)

    if provider == "local":
        model_name = os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        return LocalEmbeddingsProvider(model_name=model_name, dimension=embedding_dim)

    raise ValueError("EMBEDDING_PROVIDER must be one of: gemini, openai, local")
