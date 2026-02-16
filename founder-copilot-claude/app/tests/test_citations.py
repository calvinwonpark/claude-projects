from dataclasses import replace

import app.rag as rag_module
from app.config import settings
from app.rag import RetrievedDoc, apply_citation_mode


def docs():
    return [
        RetrievedDoc(
            doc_id="tech/architecture_patterns.md",
            title="Architecture Patterns",
            source="tech/architecture_patterns.md",
            chunk_index=0,
            content="Use modular architecture.",
            score=0.8,
        )
    ]


def _settings_with_mode(mode: str):
    return replace(settings, safety=replace(settings.safety, citation_mode=mode))


def test_strict_refuses_without_citation(monkeypatch):
    monkeypatch.setattr(rag_module, "settings", _settings_with_mode("strict"))
    answer, citations, verification = apply_citation_mode("Use modular architecture.", docs(), "question")
    assert verification == "insufficient_evidence"
    assert citations == []
    assert "enough evidence" in answer.lower()


def test_strict_accepts_valid_path_citation(monkeypatch):
    monkeypatch.setattr(rag_module, "settings", _settings_with_mode("strict"))
    answer, citations, verification = apply_citation_mode(
        "Use modular architecture for scaling [doc:tech/architecture_patterns.md].",
        docs(),
        "question",
    )
    assert verification == "verified"
    assert citations == ["doc:tech/architecture_patterns.md"]
    assert answer.startswith("Use modular")


def test_lenient_marks_unverified(monkeypatch):
    monkeypatch.setattr(rag_module, "settings", _settings_with_mode("lenient"))
    answer, citations, verification = apply_citation_mode("Use modular architecture.", docs(), "question")
    assert verification == "unverified"
    assert answer.startswith("[Unverified]")
    assert citations == []
