"""Tests for suite loading and Case validation."""

from evalkit.runners.runner import load_suite
from evalkit.types import Case


def test_load_rag_core():
    cases = load_suite("cases/suites/rag_core.jsonl")
    assert len(cases) >= 10
    for c in cases:
        assert isinstance(c, Case)
        assert c.id
        assert c.category == "rag"
        assert c.input.prompt


def test_load_tool_use():
    cases = load_suite("cases/suites/tool_use.jsonl")
    assert len(cases) >= 10
    for c in cases:
        assert c.category == "tool"


def test_load_refusal():
    cases = load_suite("cases/suites/refusal.jsonl")
    assert len(cases) >= 10


def test_load_injection():
    cases = load_suite("cases/suites/prompt_injection.jsonl")
    assert len(cases) >= 10


def test_load_multilingual():
    cases = load_suite("cases/suites/multilingual_ko_en.jsonl")
    assert len(cases) >= 10
    # Check that some cases have Korean language
    ko_cases = [c for c in cases if c.input.language == "ko"]
    assert len(ko_cases) >= 3
