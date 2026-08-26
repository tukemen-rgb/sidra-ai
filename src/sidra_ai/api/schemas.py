"""Request/response models for the private API."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

# Keep repository-scoped API work bounded within a single authenticated request.
# The v0.1 allowlist is small; these limits leave headroom without permitting an
# attacker-sized list/name to amplify validation, retrieval, or GitHub ingestion.
MAX_REPOSITORY_SCOPE_ITEMS = 32
MAX_REPOSITORY_NAME_CHARS = 200
RepositoryRef = Annotated[
    str,
    Field(min_length=3, max_length=MAX_REPOSITORY_NAME_CHARS),
]


def _validate_repository_scope(
    repositories: list[str] | None,
) -> list[str] | None:
    """Reject duplicate logical repositories before service work begins.

    GitHub repository identifiers are case-insensitive for SIDRA's allowlist
    checks. Repeating the same logical repository under different casing must
    therefore not multiply ingestion or retrieval work within one request.
    """

    if repositories is None:
        return None

    normalized = [repository.casefold() for repository in repositories]
    if len(normalized) != len(set(normalized)):
        raise ValueError("repositories must not contain duplicates")
    return repositories


#: Replayed conversation is bounded harder than the current message. The
#: message is sent once; every history turn is re-sent on every follow-up, so
#: an unbounded history is a way to grow one request's prompt without limit.
#: Eight turns is enough to keep an investigation coherent and small enough
#: that the whole exchange still fits beside the retrieved evidence.
MAX_HISTORY_TURNS = 8
MAX_HISTORY_TURN_CHARS = 8_000


class ChatTurn(BaseModel):
    """One completed exchange, as the client remembers it.

    Both sides are the client's claim, not SIDRA's record: the API keeps no
    session state in v0.1. They are screened and enveloped as untrusted DATA.
    """

    question: str = Field(min_length=1, max_length=MAX_HISTORY_TURN_CHARS)
    answer: str = Field(min_length=1, max_length=MAX_HISTORY_TURN_CHARS)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
    top_k: int = Field(default=5, ge=1, le=20)
    history: list[ChatTurn] | None = Field(
        default=None,
        max_length=MAX_HISTORY_TURNS,
        description=(
            "Earlier turns of this conversation, oldest first. Treated as "
            "untrusted DATA, never as instructions."
        ),
    )
    repositories: list[RepositoryRef] | None = Field(
        default=None,
        max_length=MAX_REPOSITORY_SCOPE_ITEMS,
        description="Restrict retrieval to these repositories. Allowlisted only.",
    )

    @field_validator("repositories")
    @classmethod
    def validate_repository_scope(cls, value: list[str] | None) -> list[str] | None:
        return _validate_repository_scope(value)


#: How much of a cited chunk /v1/chat may show as evidence.
#:
#: Every character here is content leaving the process, so the cap is a
#: security parameter and not a formatting preference: it is pinned by a test
#: so that widening the export surface has to be a deliberate, reviewed edit
#: rather than a number somebody nudges while tuning readability.
MAX_CITATION_EXCERPT_CHARS = 200


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
    #: The opening of the cited chunk, so an operator can check the answer
    #: against its evidence instead of taking repo/path/rank on faith.
    #: Empty when the excerpt was withheld - see ``excerpt_withheld``.
    excerpt: str = ""
    #: True when evidence exists but the output guard refused to show it.
    #: Distinguishing this from an empty chunk matters: "we are not showing
    #: you this" and "there is nothing here" would otherwise look identical.
    excerpt_withheld: bool = False


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=32_000)
    top_k: int = Field(default=5, ge=1, le=20)
    repositories: list[RepositoryRef] | None = Field(
        default=None,
        max_length=MAX_REPOSITORY_SCOPE_ITEMS,
        description="Restrict retrieval to these repositories. Allowlisted only.",
    )

    @field_validator("repositories")
    @classmethod
    def validate_repository_scope(cls, value: list[str] | None) -> list[str] | None:
        return _validate_repository_scope(value)


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
    #: How the message was classified, and what happened if it was routed to
    #: a generator. Present on every answered turn so a caller can tell a
    #: question that was answered from a creation request that fell back to
    #: being answered - the two look identical without it. Carries matched
    #: keywords from a fixed table, never the operator's own text.
    creation: dict[str, Any] = Field(default_factory=dict)


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

    @field_validator("repositories")
    @classmethod
    def validate_repository_scope(cls, value: list[str] | None) -> list[str] | None:
        return _validate_repository_scope(value)


class AnalyzeResponse(BaseModel):
    ingestion: dict[str, Any]
    inference_skipped: bool
    reason: str = ""
    analysis: dict[str, Any] | None = None


class RepositoryIndexSummary(BaseModel):
    """What SIDRA holds for one repository. Counts and cursors, never content."""

    repository: str
    documents: int = 0
    source_types: dict[str, int] = Field(default_factory=dict)
    last_ingested_at: str = ""
    last_commit_sha: str = ""
    quarantined: int = 0
    has_error: bool = False
    """Whether the last ingestion recorded an error.

    Deliberately a flag rather than the message. ``RepositoryState.last_error``
    holds up to 500 characters of an exception string that may quote a GitHub
    response, and this endpoint is a reporting surface, not a debugging one.
    """


class QuarantineSummary(BaseModel):
    """Counts from the quarantine audit log, or an honest failure to read it."""

    available: bool = True
    total: int = 0
    releasable: int = 0
    released: int = 0
    pending: int = 0
    by_decision: dict[str, int] = Field(default_factory=dict)
    by_finding_category: dict[str, int] = Field(default_factory=dict)


class AuditDurabilitySummary(BaseModel):
    """Whether the audit sink is actually keeping what it is handed.

    Audit writes are best-effort so a disk fault cannot turn a safe answer
    into an HTTP error. Without these counts that trade is invisible: a lost
    record looks exactly like an operation that never happened, which is the
    reading an attacker would prefer an operator to make.

    ``last_failure_kind`` carries an exception class name only. The message
    would name the audit path.
    """

    recorded: int = 0
    failed: int = 0
    last_failure_kind: str = ""


class IndexResponse(BaseModel):
    """What is in the index, so an operator can tell a thin answer from a gap.

    No document text, paths, URLs or authors appear here. Retrieval with
    citations is ``/v1/retrieve``'s job; this answers "what does SIDRA know
    about at all", which is the question you ask when an answer looks wrong.
    """

    documents: int = 0
    chunks: int = 0
    redacted_documents: int = 0
    source_types: dict[str, int] = Field(default_factory=dict)
    repositories: list[RepositoryIndexSummary] = Field(default_factory=list)
    quarantine: QuarantineSummary = Field(default_factory=QuarantineSummary)
    audit: AuditDurabilitySummary = Field(default_factory=AuditDurabilitySummary)


class HealthResponse(BaseModel):
    """Unauthenticated liveness/readiness summary with no topology details."""

    status: str
    version: str
    model_available: bool
    github_write_enabled: bool = False
