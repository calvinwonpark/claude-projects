from __future__ import annotations

from dataclasses import dataclass

from app.models.bug import NormalizedBug


@dataclass(frozen=True)
class _DomainRule:
    id: str
    keywords: list[str]


_DOMAIN_RULES: list[_DomainRule] = [
    _DomainRule(
        id="digital-rooms",
        keywords=[
            "digital-room",
            "digital room",
            "room page",
            "room-content",
            "external share",
            "sharing link",
            "room rendering",
        ],
    ),
    _DomainRule(
        id="pitch-data",
        keywords=[
            "pitch",
            "pitch-data",
            "pitch deck",
            "pitch-renderer",
            "slides",
            "pitchdata",
            "pitch content",
        ],
    ),
]


def detect_domains(bug: NormalizedBug) -> list[str]:
    corpus = " ".join(
        [
            bug.title,
            bug.summary,
            *bug.component,
            *bug.labels,
            bug.actual_behavior,
            *bug.comments,
        ]
    ).lower()

    return [
        rule.id
        for rule in _DOMAIN_RULES
        if any(kw in corpus for kw in rule.keywords)
    ]
