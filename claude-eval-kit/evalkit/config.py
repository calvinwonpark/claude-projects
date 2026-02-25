"""Centralized configuration loaded from environment."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: str = Field(default="offline", alias="MODE")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    judge_model: str = Field(default="claude-haiku-4-5-20251001", alias="JUDGE_MODEL")
    target_model: str = Field(default="claude-sonnet-4-5-20250929", alias="TARGET_MODEL")
    http_endpoint: str = Field(default="http://localhost:8000/api/eval", alias="HTTP_ENDPOINT")
    timeout_s: int = Field(default=30, alias="TIMEOUT_S")
    concurrency: int = Field(default=4, alias="CONCURRENCY")
    max_cases: int = Field(default=0, alias="MAX_CASES")
    cost_per_1k_input: float = Field(default=0.003, alias="COST_PER_1K_INPUT")
    cost_per_1k_output: float = Field(default=0.015, alias="COST_PER_1K_OUTPUT")
    baseline_dir: Path = Field(default=Path("baselines/main"), alias="BASELINE_DIR")
    runs_dir: Path = Field(default=Path("runs"), alias="RUNS_DIR")
    sanitize_logs: bool = Field(default=True, alias="SANITIZE_LOGS")


settings = Settings()
