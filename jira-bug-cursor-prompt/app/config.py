from __future__ import annotations

import os


ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
USE_MOCK_JIRA: bool = os.getenv("USE_MOCK_JIRA", "true").lower() in ("true", "1", "yes")
