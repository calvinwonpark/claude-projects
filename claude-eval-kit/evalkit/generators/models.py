"""Pydantic models for app specs, generated eval cases, and generation results."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# App Spec — describes the app under evaluation
# ---------------------------------------------------------------------------


class AppSpec(BaseModel):
    """Structured description of an app for eval case generation."""

    app_name: str
    app_description: str
    agents: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    docs: list[str] = Field(default_factory=list)
    supported_categories: list[str] = Field(default_factory=list)
    response_contract: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    example_prompts: list[str] = Field(default_factory=list)

    @field_validator("supported_categories", mode="before")
    @classmethod
    def _lowercase_categories(cls, v: list[str]) -> list[str]:
        return [c.lower().strip() for c in v]

    @classmethod
    def from_yaml(cls, path: str | Path) -> AppSpec:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)


# ---------------------------------------------------------------------------
# Generated eval case — compatible with evalkit.types.Case
# ---------------------------------------------------------------------------


class GeneratedCaseInput(BaseModel):
    prompt: str
    language: str = "en"


class GeneratedCaseExpectations(BaseModel):
    expected_agent: Optional[str] = None
    expected_tools: Optional[list[str]] = None
    required_citations: Optional[bool] = None
    expected_refusal: Optional[bool] = None
    gold_doc_ids: Optional[list[str]] = None
    latency_budget_ms: Optional[float] = None
    notes: Optional[str] = None


class GeneratedCase(BaseModel):
    """A single generated eval case. Serializes to the evalkit JSONL format."""

    id: str
    category: str
    input: GeneratedCaseInput
    expectations: GeneratedCaseExpectations = Field(
        default_factory=GeneratedCaseExpectations
    )
    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

    def to_jsonl_dict(self) -> dict[str, Any]:
        """Serialize to the dict format used in evalkit JSONL suites."""
        d: dict[str, Any] = {
            "id": self.id,
            "category": self.category,
            "input": self.input.model_dump(exclude_none=True),
            "expectations": self.expectations.model_dump(exclude_none=True),
        }
        if self.tags:
            d["tags"] = self.tags
        if self.notes:
            d["notes"] = self.notes
        return d


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    case_id: str
    field: str
    message: str
    severity: str = "error"  # error | warning


class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# Generation summary
# ---------------------------------------------------------------------------


class GenerationSummary(BaseModel):
    app_name: str
    category: str
    generated_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    duplicate_count: int = 0
    written_path: Optional[str] = None
    issues: list[ValidationIssue] = Field(default_factory=list)

    def print_report(self) -> str:
        lines = [
            f"Generation Summary: {self.app_name} / {self.category}",
            f"  Generated:  {self.generated_count}",
            f"  Valid:      {self.valid_count}",
            f"  Invalid:    {self.invalid_count}",
            f"  Duplicates: {self.duplicate_count}",
        ]
        if self.written_path:
            lines.append(f"  Written to: {self.written_path}")
        if self.issues:
            lines.append(f"  Issues:")
            for issue in self.issues:
                lines.append(
                    f"    [{issue.severity}] {issue.case_id}.{issue.field}: {issue.message}"
                )
        return "\n".join(lines)
