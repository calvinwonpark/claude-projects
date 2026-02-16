import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from app import db

STATE_DIR = Path(os.getenv("STATE_DIR", "state"))
STATE_PATH = STATE_DIR / "copilot_state.json"
_LOCK = Lock()


def _ensure() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, Any]:
    _ensure()
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(data: dict[str, Any]) -> None:
    _ensure()
    with _LOCK:
        STATE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def append_audit_log(row: dict[str, Any]) -> None:
    try:
        db.insert_audit(row)
        return
    except Exception:
        # Fallback to local state for dev bootstrapping if DB is unavailable.
        state = load_state()
        logs = state.setdefault("audit_logs", [])
        logs.append(row)
        state["audit_logs"] = logs[-5000:]
        save_state(state)


def get_recent_audit_logs(limit: int = 50) -> list[dict[str, Any]]:
    try:
        return db.recent_audit(limit)
    except Exception:
        state = load_state()
        logs = state.get("audit_logs", [])
        safe_limit = max(1, min(limit, 200))
        return list(reversed(logs[-safe_limit:]))
