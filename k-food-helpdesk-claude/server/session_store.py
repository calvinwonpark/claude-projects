import json
import os
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol


@dataclass
class SessionTurn:
    role: str
    text: str
    ts: float = field(default_factory=time.time)


@dataclass
class SessionState:
    turns: list[SessionTurn] = field(default_factory=list)
    retrieval_cache: dict[str, list[int]] = field(default_factory=dict)
    target_language: str | None = None


class SessionStore(Protocol):
    def get(self, session_id: str) -> SessionState:
        ...

    def upsert(self, session_id: str, state: SessionState) -> None:
        ...


class InMemorySessionStore:
    def __init__(self, max_turns: int = 20) -> None:
        self._max_turns = max_turns
        self._lock = Lock()
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        with self._lock:
            return self._sessions.get(session_id, SessionState())

    def upsert(self, session_id: str, state: SessionState) -> None:
        state.turns = state.turns[-self._max_turns :]
        with self._lock:
            self._sessions[session_id] = state


class RedisSessionStore:
    """Stubbed Redis-backed session store interface for production deployments."""

    def __init__(self, redis_url: str, max_turns: int = 20) -> None:
        import redis

        self._max_turns = max_turns
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = 60 * 60 * 24

    def get(self, session_id: str) -> SessionState:
        raw = self._redis.get(self._key(session_id))
        if not raw:
            return SessionState()
        data = json.loads(raw)
        turns = [SessionTurn(**t) for t in data.get("turns", [])]
        return SessionState(
            turns=turns[-self._max_turns :],
            retrieval_cache=data.get("retrieval_cache", {}),
            target_language=data.get("target_language"),
        )

    def upsert(self, session_id: str, state: SessionState) -> None:
        state.turns = state.turns[-self._max_turns :]
        payload = {
            "turns": [t.__dict__ for t in state.turns],
            "retrieval_cache": state.retrieval_cache,
            "target_language": state.target_language,
        }
        self._redis.setex(self._key(session_id), self._ttl_seconds, json.dumps(payload))

    @staticmethod
    def _key(session_id: str) -> str:
        return f"kfh:session:{session_id}"


def build_session_store() -> SessionStore:
    max_turns = int(os.getenv("SESSION_MAX_TURNS", "20"))
    backend = os.getenv("SESSION_STORE_BACKEND", "memory").lower()
    if backend == "redis":
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        return RedisSessionStore(redis_url=redis_url, max_turns=max_turns)
    return InMemorySessionStore(max_turns=max_turns)
