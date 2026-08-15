"""Request/response models for the private API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
    top_k: int = Field(default=5, ge=1, le=20)
    repositories: list[str] | None = Field(
        default=None,
        description="Restrict retrieval to these repositories. Allowlisted only.",
    )


class Citation(BaseModel):
    label: str
    citation: str
    repository: str
    path: str
    commit_sha: str
    source_type: str
    trust_level: str
    license: str
    url: str = ""
    redacted: bool = False


class ChatResponse(BaseModel):
    answer: str
    refused: bool = False
    reason: str = ""
    citations: list[Citation] = Field(default_factory=list)
    security: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, Any] = Field(default_factory=dict)


class AnalyzeRequest(BaseModel):
    repositories: list[str] | None = Field(
        default=None, description="Defaults to every allowlisted repository."
    )
    force: bool = Field(
        default=False,
        description="Re-ingest even when the commit SHA is unchanged.",
    )
    question: str = Field(default="", max_length=4_000)


class AnalyzeResponse(BaseModel):
    ingestion: dict[str, Any]
    inference_skipped: bool
    reason: str = ""
    analysis: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    model: dict[str, Any]
    index: dict[str, Any]
    config: dict[str, Any]
    github_write_enabled: bool = False
