from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


def _as_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _as_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: str
    primary_model: str
    fallback_model: str
    model_candidates: list[str]
    temperature: float
    max_output_tokens: int
    request_timeout_ms: int


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int
    min_score: float
    max_context_chars: int
    rerank_mode: str
    lexical_fallback: bool


@dataclass(frozen=True)
class RouterConfig:
    strategy: str
    auto_high_conf: float
    auto_gap: float
    auto_mid_conf: float


@dataclass(frozen=True)
class SafetyConfig:
    citation_mode: str
    strict_stream_buffered: bool
    strict_claim_check: bool
    pii_redaction: bool


@dataclass(frozen=True)
class ToolConfig:
    max_iters: int
    timeout_ms: int


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    enable_audit_logs: bool


@dataclass(frozen=True)
class AppConfig:
    anthropic: AnthropicConfig
    retrieval: RetrievalConfig
    router: RouterConfig
    safety: SafetyConfig
    tools: ToolConfig
    logging: LoggingConfig
    embedding_provider: str
    auth_mode: str
    redis_url: str

    @staticmethod
    def load() -> "AppConfig":
        candidates = [m.strip() for m in os.getenv("CLAUDE_MODEL_CANDIDATES", "").split(",") if m.strip()]
        return AppConfig(
            anthropic=AnthropicConfig(
                api_key=os.getenv("ANTHROPIC_API_KEY", ""),
                primary_model=os.getenv("CLAUDE_PRIMARY_MODEL", "claude-3-5-sonnet-latest"),
                fallback_model=os.getenv("CLAUDE_FALLBACK_MODEL", "claude-3-5-haiku-latest"),
                model_candidates=candidates,
                temperature=_as_float("CLAUDE_TEMPERATURE", 0.2),
                max_output_tokens=_as_int("MAX_OUTPUT_TOKENS", 1000),
                request_timeout_ms=_as_int("REQUEST_TIMEOUT_MS", 20000),
            ),
            retrieval=RetrievalConfig(
                top_k=_as_int("RETRIEVAL_TOP_K", 8),
                min_score=_as_float("RETRIEVAL_MIN_SCORE", 0.2),
                max_context_chars=_as_int("RAG_MAX_CONTEXT_CHARS", 7000),
                rerank_mode=os.getenv("RERANK_MODE", "heuristic").lower(),
                lexical_fallback=_as_bool("RETRIEVAL_ENABLE_LEXICAL_FALLBACK", True),
            ),
            router=RouterConfig(
                strategy=os.getenv("ROUTER_STRATEGY", "auto").lower(),
                auto_high_conf=_as_float("ROUTER_AUTO_HIGH_CONF", 0.65),
                auto_gap=_as_float("ROUTER_AUTO_GAP", 0.20),
                auto_mid_conf=_as_float("ROUTER_AUTO_MID_CONF", 0.45),
            ),
            safety=SafetyConfig(
                citation_mode=os.getenv("CITATION_MODE", "strict").lower(),
                strict_stream_buffered=_as_bool("STRICT_STREAM_BUFFERED", True),
                strict_claim_check=_as_bool("STRICT_CLAIM_CHECK", False),
                pii_redaction=_as_bool("PII_REDACTION", True),
            ),
            tools=ToolConfig(
                max_iters=_as_int("TOOL_MAX_ITERS", 3),
                timeout_ms=_as_int("TOOL_TIMEOUT_MS", 3000),
            ),
            logging=LoggingConfig(
                level=os.getenv("LOG_LEVEL", "INFO"),
                enable_audit_logs=_as_bool("ENABLE_AUDIT_LOGS", True),
            ),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "local"),
            auth_mode=os.getenv("AUTH_MODE", "none"),
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        )


settings = AppConfig.load()
