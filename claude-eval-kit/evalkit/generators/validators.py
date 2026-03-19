"""Deterministic validation for generated eval cases.

Validates generated cases against the app spec inventory before they
are written to JSONL. No LLM involved — purely structural checks.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Optional

from evalkit.generators.models import (
    AppSpec,
    GeneratedCase,
    ValidationIssue,
    ValidationResult,
)


def validate_case(case: GeneratedCase, app: AppSpec) -> ValidationResult:
    """Validate a single generated case against the app spec."""
    issues: list[ValidationIssue] = []

    if not case.id or not case.id.strip():
        issues.append(ValidationIssue(
            case_id=case.id or "<empty>",
            field="id",
            message="Case ID is empty",
        ))

    if case.category not in app.supported_categories:
        issues.append(ValidationIssue(
            case_id=case.id,
            field="category",
            message=f"Category '{case.category}' not in supported: {app.supported_categories}",
        ))

    if not case.input.prompt or not case.input.prompt.strip():
        issues.append(ValidationIssue(
            case_id=case.id,
            field="input.prompt",
            message="Prompt is empty",
        ))

    exp = case.expectations

    if exp.expected_agent is not None and app.agents:
        if exp.expected_agent not in app.agents:
            issues.append(ValidationIssue(
                case_id=case.id,
                field="expectations.expected_agent",
                message=f"Agent '{exp.expected_agent}' not in app agents: {app.agents}",
            ))

    if exp.expected_tools is not None and app.tools:
        for tool in exp.expected_tools:
            if tool not in app.tools:
                issues.append(ValidationIssue(
                    case_id=case.id,
                    field="expectations.expected_tools",
                    message=f"Tool '{tool}' not in app tools: {app.tools}",
                ))

    if exp.gold_doc_ids is not None and app.docs:
        for doc_id in exp.gold_doc_ids:
            if doc_id not in app.docs:
                issues.append(ValidationIssue(
                    case_id=case.id,
                    field="expectations.gold_doc_ids",
                    message=f"Doc '{doc_id}' not in app docs: {app.docs}",
                ))

    if exp.latency_budget_ms is not None and exp.latency_budget_ms <= 0:
        issues.append(ValidationIssue(
            case_id=case.id,
            field="expectations.latency_budget_ms",
            message=f"Latency budget must be positive, got {exp.latency_budget_ms}",
            severity="warning",
        ))

    valid = len([i for i in issues if i.severity == "error"]) == 0
    return ValidationResult(valid=valid, issues=issues)


def validate_batch(
    cases: list[GeneratedCase],
    app: AppSpec,
    existing_ids: Optional[set[str]] = None,
) -> tuple[list[GeneratedCase], list[GeneratedCase], list[ValidationIssue]]:
    """Validate a batch of cases. Returns (valid, invalid, all_issues).

    Also checks for:
    - Duplicate IDs within the batch
    - Duplicate IDs against existing_ids
    - Near-duplicate prompts (similarity > 0.85)
    """
    valid_cases: list[GeneratedCase] = []
    invalid_cases: list[GeneratedCase] = []
    all_issues: list[ValidationIssue] = []

    seen_ids: set[str] = set(existing_ids or set())
    seen_prompts: list[str] = []

    for case in cases:
        result = validate_case(case, app)

        if case.id in seen_ids:
            result.issues.append(ValidationIssue(
                case_id=case.id,
                field="id",
                message=f"Duplicate ID: '{case.id}'",
            ))
            result.valid = False

        dupe_prompt = _find_near_duplicate(case.input.prompt, seen_prompts)
        if dupe_prompt is not None:
            result.issues.append(ValidationIssue(
                case_id=case.id,
                field="input.prompt",
                message=f"Near-duplicate prompt (similarity > 0.85)",
                severity="warning",
            ))

        all_issues.extend(result.issues)

        if result.valid:
            valid_cases.append(case)
            seen_ids.add(case.id)
            seen_prompts.append(case.input.prompt)
        else:
            invalid_cases.append(case)

    return valid_cases, invalid_cases, all_issues


def _find_near_duplicate(
    prompt: str,
    existing: list[str],
    threshold: float = 0.85,
) -> Optional[str]:
    """Check if prompt is near-duplicate of any existing prompt."""
    prompt_lower = prompt.lower().strip()
    for existing_prompt in existing:
        ratio = SequenceMatcher(
            None, prompt_lower, existing_prompt.lower().strip()
        ).ratio()
        if ratio > threshold:
            return existing_prompt
    return None
