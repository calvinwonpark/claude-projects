from functools import lru_cache
import os

from pydantic import Field
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover - allow offline eval without optional dependency
    from pydantic import BaseModel as BaseSettings

    class SettingsConfigDict(dict):
        pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TeachMe Live Claude"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model_primary: str = Field(default="claude-sonnet-4-5-20250929", alias="ANTHROPIC_MODEL_PRIMARY")
    anthropic_model_fallback: str = Field(default="claude-haiku-4-5-20251001", alias="ANTHROPIC_MODEL_FALLBACK")
    llm_max_tokens: int = Field(default=600, alias="LLM_MAX_TOKENS")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_request_timeout_ms: int = Field(default=20000, alias="LLM_REQUEST_TIMEOUT_MS")
    time_budget_ms: int = Field(default=8000, alias="TIME_BUDGET_MS")
    image_time_budget_ms: int = Field(default=18000, alias="IMAGE_TIME_BUDGET_MS")

    strict_structured_mode: bool = Field(default=True, alias="STRICT_STRUCTURED_MODE")
    tool_max_iters: int = Field(default=2, alias="TOOL_MAX_ITERS")
    tool_timeout_ms: int = Field(default=3000, alias="TOOL_TIMEOUT_MS")
    turn_max_seconds: int = Field(default=20, alias="TURN_MAX_SECONDS")
    turn_silence_ms: int = Field(default=1200, alias="TURN_SILENCE_MS")
    stt_confidence_threshold: float = Field(default=0.55, alias="STT_CONFIDENCE_THRESHOLD")
    max_audio_bytes: int = Field(default=2_400_000, alias="MAX_AUDIO_BYTES")

    stt_sample_rate_hz: int = Field(default=16000, alias="STT_SAMPLE_RATE_HZ")
    tts_sample_rate_hz: int = Field(default=24000, alias="TTS_SAMPLE_RATE_HZ")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except Exception:
        # Fallback path when pydantic-settings is unavailable.
        return Settings(
            app_name=os.getenv("APP_NAME", "TeachMe Live Claude"),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model_primary=os.getenv("ANTHROPIC_MODEL_PRIMARY", "claude-sonnet-4-5-20250929"),
            anthropic_model_fallback=os.getenv("ANTHROPIC_MODEL_FALLBACK", "claude-haiku-4-5-20251001"),
            llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "600")),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            llm_request_timeout_ms=int(os.getenv("LLM_REQUEST_TIMEOUT_MS", "20000")),
            time_budget_ms=int(os.getenv("TIME_BUDGET_MS", "8000")),
            image_time_budget_ms=int(os.getenv("IMAGE_TIME_BUDGET_MS", "18000")),
            strict_structured_mode=os.getenv("STRICT_STRUCTURED_MODE", "true").lower() == "true",
            tool_max_iters=int(os.getenv("TOOL_MAX_ITERS", "2")),
            tool_timeout_ms=int(os.getenv("TOOL_TIMEOUT_MS", "3000")),
            turn_max_seconds=int(os.getenv("TURN_MAX_SECONDS", "20")),
            turn_silence_ms=int(os.getenv("TURN_SILENCE_MS", "1200")),
            stt_confidence_threshold=float(os.getenv("STT_CONFIDENCE_THRESHOLD", "0.55")),
            max_audio_bytes=int(os.getenv("MAX_AUDIO_BYTES", "2400000")),
            stt_sample_rate_hz=int(os.getenv("STT_SAMPLE_RATE_HZ", "16000")),
            tts_sample_rate_hz=int(os.getenv("TTS_SAMPLE_RATE_HZ", "24000")),
        )


settings = get_settings()
