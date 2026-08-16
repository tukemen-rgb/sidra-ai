"""Request/response models for the private API."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field

# Keep repository-scoped API work bounded within a single authenticated request.
# The v0.1 allowlist is small; these limits leave headroom without permitting an
# attacker-sized list/name to amplify validation, retrieval, or GitHub ingestion.
MAX_REPOSITORY_SCOPE_ITEMS = 32
MAX_REPOSITORY_NAME_CHARS = 200
RepositoryRef = Annotated[
    str,
    Field(min_length=3, max_length=MAX_REPOSITORY_NAME_CHARS),
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
    top_k: int = Field(default=5, ge=1, le=20)
    repositories: list[RepositoryRef] | None = Field(
        default=None,
        max_length=MAX_REPOSITORY_SCOPE_ITEMS,
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


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=32_000)
    top_k: int = Field(default=5, ge=1, le=20)
    repositories: list[RepositoryRef] | None = Field(
        default=None,
        max_length=MAX_REPOSITORY_SCOPE_ITEMS,
        description="Restrict retrieval to these repositories. Allowlisted only.",
    )


class RetrieveResult(BaseModel):
    score: float
    citation: Citation


class RetrieveResponse(BaseModel):
    refused: bool = False
    reason: str = ""
    results: list[RetrieveResult] = Field(default_factory=list)
    security: dict[str, Any] = Field(default_factory=dict)
    model_invoked: bool = False
    external_api_cost_usd: float = 0.0


class ChatResponse(BaseModel):
    answer: str
    refused: bool = False
    reason: str = ""
    citations: list[Citation] = Field(default_factory=list)
    security: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, Any] = Field(default_factory=dict)


class AnalyzeRequest(BaseModel):
    repositories: list[RepositoryRef] | None = Field(
        default=None,
        max_length=MAX_REPOSITORY_SCOPE_ITEMS,
        description="Defaults to every allowlisted repository.",
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
    """Unauthenticated liveness/readiness summary with no topology details."""

    status: str
    version: str
    model_available: bool
    github_write_enabled: bool = False
