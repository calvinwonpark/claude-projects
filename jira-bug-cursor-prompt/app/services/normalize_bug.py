from __future__ import annotations

import re

from app.models.bug import NormalizedBug
from app.models.jira import JiraBug


def _extract_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"##\s*{re.escape(heading)}\s*\n([\s\S]*?)(?=\n##\s|$)", re.IGNORECASE
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _extract_numbered_list(text: str) -> list[str]:
    return [
        re.sub(r"^\d+\.\s*", "", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]


_ISSUE_REF = re.compile(r"\b[A-Z]+-\d+\b")


def normalize_bug(raw: JiraBug) -> NormalizedBug:
    desc = raw.fields.description or ""

    repro_section = _extract_section(desc, "Steps to Reproduce")
    repro_steps = _extract_numbered_list(repro_section) if repro_section else []

    comment_texts = [
        f"[{c.author.display_name}] {c.body}" for c in raw.fields.comments
    ]

    all_text = desc + " " + " ".join(comment_texts)
    linked_docs = sorted(
        {ref for ref in _ISSUE_REF.findall(all_text) if ref != raw.key}
    )

    return NormalizedBug(
        bug_id=raw.key,
        title=raw.fields.summary or "Untitled",
        summary=_extract_section(desc, "Description") or desc[:500],
        severity=raw.fields.priority or "Unknown",
        component=raw.fields.components,
        labels=raw.fields.labels,
        environment=raw.fields.environment or "Not specified",
        repro_steps=repro_steps,
        expected_behavior=_extract_section(desc, "Expected Behavior"),
        actual_behavior=_extract_section(desc, "Actual Behavior"),
        comments=comment_texts,
        linked_docs=linked_docs,
        constraints=[],
    )
