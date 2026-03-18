from __future__ import annotations

from pydantic import BaseModel, Field


class JiraUser(BaseModel):
    account_id: str
    display_name: str
    email: str | None = None


class JiraComment(BaseModel):
    id: str
    author: JiraUser
    body: str
    created: str
    updated: str


class JiraIssueFields(BaseModel):
    summary: str = ""
    description: str | None = None
    status: str = "Unknown"
    priority: str = "Unknown"
    issue_type: str = "Bug"
    components: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    environment: str | None = None
    reporter: JiraUser | None = None
    assignee: JiraUser | None = None
    created: str = ""
    updated: str = ""
    comments: list[JiraComment] = Field(default_factory=list)


class JiraBug(BaseModel):
    key: str
    id: str
    self_url: str = ""
    fields: JiraIssueFields
