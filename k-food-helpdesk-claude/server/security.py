import os
import re
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)\d{3,4}[-.\s]?\d{4}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


@dataclass
class AuthContext:
    user_id: str | None
    auth_mode: str


def redact_pii(text: str) -> str:
    masked = EMAIL_RE.sub("[REDACTED_EMAIL]", text or "")
    masked = PHONE_RE.sub("[REDACTED_PHONE]", masked)
    masked = CARD_RE.sub("[REDACTED_CARD]", masked)
    return masked


def maybe_redact(text: str) -> str:
    if os.getenv("PII_REDACTION", "true").lower() == "true":
        return redact_pii(text)
    return text


def _decode_bearer(auth_header: str) -> dict:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization Bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET is not configured")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid JWT token")


def require_auth(
    authorization: str | None = Header(default=None),
) -> AuthContext:
    mode = os.getenv("AUTH_MODE", "none").lower()
    if mode == "none":
        return AuthContext(user_id=None, auth_mode=mode)
    if mode != "jwt":
        raise HTTPException(status_code=500, detail="AUTH_MODE must be one of: none, jwt")
    payload = _decode_bearer(authorization or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="JWT missing user_id/sub")
    return AuthContext(user_id=user_id, auth_mode=mode)


def authorize_audit_access(
    authorization: str | None,
    x_api_key: str | None,
) -> AuthContext:
    admin_api_key = os.getenv("ADMIN_API_KEY", "").strip()
    if admin_api_key and x_api_key and x_api_key == admin_api_key:
        return AuthContext(user_id="admin_api_key", auth_mode="admin_api_key")
    mode = os.getenv("AUTH_MODE", "none").lower()
    if mode == "jwt":
        return require_auth(authorization)
    raise HTTPException(status_code=401, detail="Audit endpoint requires JWT auth or valid X-API-Key")
