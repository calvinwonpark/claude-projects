from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeDoc(BaseModel):
    file_path: str
    content: str


class KnowledgeResult(BaseModel):
    domains: list[str] = Field(default_factory=list)
    docs: list[KnowledgeDoc] = Field(default_factory=list)
