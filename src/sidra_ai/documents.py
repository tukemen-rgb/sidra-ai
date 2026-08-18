"""Core RAG data structures shared by ingestion, security and retrieval.

Every unit of knowledge that enters SIDRA AI carries full provenance. A
document without provenance cannot be indexed: :class:`Provenance` is
validated on construction and :mod:`sidra_ai.retrieval.store` re-checks it
before accepting anything.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class SourceType(str, Enum):
    """What kind of artifact the content came from."""

    README = "readme"
    DOCS = "docs"
    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    # Reserved for later milestones (external research through the gate).
    WEB = "web"
    OPERATOR = "operator"


class TrustLevel(str, Enum):
    """How much authority a piece of content may ever have.

    Ordering matters: :data:`TRUST_ORDER` maps each level to an integer where
    a *lower* number means *more* trusted. Nothing below ``SYSTEM`` may ever
    be promoted into an instruction position.
    """

    SYSTEM = "system"
    """SIDRA's own policy/system prompts. The only instruction authority."""

    OPERATOR = "operator"
    """A human operator's direct request in the current session."""

    INTERNAL_REPO = "internal_repo"
    """Content authored inside SIDRA STUDIO's own allowlisted repositories."""

    EXTERNAL = "external"
    """Anything a third party can author: issue/PR bodies, comments, web."""

    UNVERIFIED = "unverified"
    """Source could not be attributed. Treated as hostile input."""


TRUST_ORDER: Mapping[TrustLevel, int] = {
    TrustLevel.SYSTEM: 0,
    TrustLevel.OPERATOR: 1,
    TrustLevel.INTERNAL_REPO: 2,
    TrustLevel.EXTERNAL: 3,
    TrustLevel.UNVERIFIED: 4,
}

#: Trust levels that are DATA only and must never be read as instructions.
DATA_ONLY_TRUST_LEVELS = frozenset(
    {TrustLevel.INTERNAL_REPO, TrustLevel.EXTERNAL, TrustLevel.UNVERIFIED}
)


def is_instruction_authority(trust_level: TrustLevel) -> bool:
    """Return ``True`` only for levels allowed to instruct the model."""

    return trust_level not in DATA_ONLY_TRUST_LEVELS


class ProvenanceError(ValueError):
    """Raised when provenance metadata is missing or inconsistent."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Provenance:
    """Where a document came from, and under what terms it may be used.

    ``license`` is intentionally required. If a repository does not declare a
    license we record ``"unknown"`` explicitly rather than dropping the field,
    so that "we never checked" is distinguishable from "there is no license".
    """

    source: str
    """Stable identifier of the origin system, e.g. ``"github"``."""

    repository: str
    """``owner/name`` of the repository the content belongs to."""

    path: str
    """Logical path inside the source, e.g. ``README.md`` or ``issue/12``."""

    commit_sha: str
    """Commit SHA the content was observed at. ``""`` is not accepted."""

    timestamp: datetime
    """When the content was authored/observed, timezone-aware UTC."""

    source_type: SourceType
    trust_level: TrustLevel
    license: str
    """SPDX id, ``"proprietary"``, or ``"unknown"``. Never empty."""

    url: str = ""
    author: str = ""
    """Best-effort author attribution. May be empty for synthesized content."""

    retrieved_at: datetime = field(default_factory=_utcnow)
    extra: Mapping[str, Any] = field(default_factory=dict)

    #: Fields that must be non-empty for a document to be indexable.
    REQUIRED_FIELDS = (
        "source",
        "repository",
        "path",
        "commit_sha",
        "timestamp",
        "source_type",
        "trust_level",
        "license",
    )

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Raise :class:`ProvenanceError` if any required field is missing."""

        for name in self.REQUIRED_FIELDS:
            value = getattr(self, name, None)
            if value is None:
                raise ProvenanceError(f"provenance field '{name}' is required")
            if isinstance(value, str) and not value.strip():
                raise ProvenanceError(f"provenance field '{name}' must not be empty")

        if not isinstance(self.source_type, SourceType):
            raise ProvenanceError("source_type must be a SourceType")
        if not isinstance(self.trust_level, TrustLevel):
            raise ProvenanceError("trust_level must be a TrustLevel")
        if not isinstance(self.timestamp, datetime):
            raise ProvenanceError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None:
            raise ProvenanceError("timestamp must be timezone-aware (UTC)")
        if "/" not in self.repository:
            raise ProvenanceError("repository must be in 'owner/name' form")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "repository": self.repository,
            "path": self.path,
            "commit_sha": self.commit_sha,
            "timestamp": self.timestamp.isoformat(),
            "source_type": self.source_type.value,
            "trust_level": self.trust_level.value,
            "license": self.license,
            "url": self.url,
            "author": self.author,
            "retrieved_at": self.retrieved_at.isoformat(),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Provenance":
        return cls(
            source=data["source"],
            repository=data["repository"],
            path=data["path"],
            commit_sha=data["commit_sha"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source_type=SourceType(data["source_type"]),
            trust_level=TrustLevel(data["trust_level"]),
            license=data["license"],
            url=data.get("url", ""),
            author=data.get("author", ""),
            retrieved_at=datetime.fromisoformat(
                data.get("retrieved_at", _utcnow().isoformat())
            ),
            extra=dict(data.get("extra", {})),
        )

    @property
    def citation(self) -> str:
        """Short human-readable citation used in API responses."""

        return f"{self.repository}@{self.commit_sha[:7]}:{self.path}"


@dataclass(frozen=True)
class Document:
    """A provenance-carrying unit of content.

    ``content`` may be the redacted form of the original. ``redacted`` records
    whether the security gate rewrote it, so downstream consumers never
    mistake a sanitized document for a verbatim one.
    """

    content: str
    provenance: Provenance
    redacted: bool = False
    security_findings: tuple[str, ...] = ()

    @property
    def doc_id(self) -> str:
        """Deterministic id: stable across runs, unique per content+logical origin."""

        digest = hashlib.sha256()
        # Keep document identity aligned with DocumentStore's logical-source
        # key. Source system and source type are provenance, not decoration:
        # two otherwise identical artifacts from distinct logical origins must
        # never alias the same document/chunk ids and overwrite each other.
        digest.update(self.provenance.source.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(self.provenance.repository.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(self.provenance.source_type.value.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(self.provenance.path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(self.provenance.commit_sha.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(self.content.encode("utf-8"))
        return digest.hexdigest()[:32]

    @property
    def is_instruction_authority(self) -> bool:
        """Documents are DATA. This is ``False`` for every ingested source."""

        return is_instruction_authority(self.provenance.trust_level)

    def with_content(self, content: str, *, redacted: bool = True) -> "Document":
        return replace(self, content=content, redacted=redacted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "redacted": self.redacted,
            "security_findings": list(self.security_findings),
            **self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class Chunk:
    """A retrievable slice of a :class:`Document`, carrying full provenance."""

    content: str
    provenance: Provenance
    document_id: str
    index: int
    redacted: bool = False

    @property
    def chunk_id(self) -> str:
        return f"{self.document_id}:{self.index}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "index": self.index,
            "content": self.content,
            "redacted": self.redacted,
            **self.provenance.to_dict(),
        }
