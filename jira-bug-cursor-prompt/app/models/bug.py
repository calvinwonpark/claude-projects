from __future__ import annotations

from pydantic import BaseModel, Field


class NormalizedBug(BaseModel):
    bug_id: str
    title: str
    summary: str
    severity: str
    component: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    environment: str = "Not specified"
    repro_steps: list[str] = Field(default_factory=list)
    expected_behavior: str = ""
    actual_behavior: str = ""
    comments: list[str] = Field(default_factory=list)
    linked_docs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
