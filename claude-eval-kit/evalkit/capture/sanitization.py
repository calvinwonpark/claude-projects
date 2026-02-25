"""Sanitize PII and sensitive data from trace logs."""

from __future__ import annotations

import re


_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"\b\d{3}[-.]?\d{3,4}[-.]?\d{4}\b")
_CARD_RE = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b")
_API_KEY_RE = re.compile(r"(sk-[a-zA-Z0-9]{20,})")


def sanitize_text(text: str) -> str:
    """Replace PII-like patterns with redaction tokens."""
    text = _EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = _PHONE_RE.sub("[PHONE_REDACTED]", text)
    text = _CARD_RE.sub("[CARD_REDACTED]", text)
    text = _API_KEY_RE.sub("[KEY_REDACTED]", text)
    return text
