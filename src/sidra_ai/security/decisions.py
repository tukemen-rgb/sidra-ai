"""Verdict vocabulary for the security gate.

The gate never silently deletes content. Every action produces a
:class:`GateResult` that records *what* was detected, *why* it mattered, and
*what* was done - so a human (or a later review pass) can audit the decision.
Sensitive values themselves are not part of that audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Decision(str, Enum):
    """What may happen to the inspected content."""

    ALLOW = "allow"
    """Safe to index and to place in a DATA envelope."""

    QUARANTINE = "quarantine"
    """Kept out of the retrieval index until human review. The audit trail
    retains findings/provenance and only a sanitized review copy; raw detected
    secrets or high-severity PII are never persisted merely for quarantine."""

    BLOCK = "block"
    """Must not be indexed and must not reach the model at all."""


#: Ordered by increasing restriction; used to combine multiple findings.
_DECISION_RANK = {Decision.ALLOW: 0, Decision.QUARANTINE: 1, Decision.BLOCK: 2}


def strictest(*decisions: Decision) -> Decision:
    """Return the most restrictive of ``decisions`` (``ALLOW`` if empty)."""

    return max(decisions, key=lambda d: _DECISION_RANK[d], default=Decision.ALLOW)


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingCategory(str, Enum):
    """The detector families required by v0.1."""

    SECRET = "secret"
    """API key, token, password or private key material."""

    PII = "pii"
    """Personal information: email, phone, national/credit numbers."""

    PROMPT_INJECTION = "prompt_injection"
    """Text attempting to act as an instruction rather than as data."""

    OVERSIZED_INPUT = "oversized_input"
    """Input beyond the configured byte budget."""

    UNPERMITTED_SOURCE = "unpermitted_source"
    """Content from a repository/source not on the allowlist."""

    MALFORMED = "malformed"
    """Content that could not be interpreted safely (e.g. bad encoding)."""


@dataclass(frozen=True)
class Finding:
    """A single detection.

    ``evidence`` is always a redacted excerpt. A finding must never carry the
    secret it reports - that would just move the leak into the audit log.
    """

    category: FindingCategory
    severity: Severity
    detector: str
    reason: str
    evidence: str = ""
    start: int = -1
    end: int = -1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "detector": self.detector,
            "reason": self.reason,
            "evidence": self.evidence,
            "start": self.start,
            "end": self.end,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GateResult:
    """Outcome of inspecting one piece of content."""

    decision: Decision
    findings: tuple[Finding, ...]
    content: str
    """The content as it may be used downstream. Redacted when ``redacted``."""

    original_length: int
    redacted: bool = False
    reasons: tuple[str, ...] = ()
    inspected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    @property
    def indexable(self) -> bool:
        """Only ``ALLOW`` content reaches the retrieval index."""

        return self.decision is Decision.ALLOW

    def findings_by_category(self, category: FindingCategory) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.category is category)

    def has(self, category: FindingCategory) -> bool:
        return any(f.category is category for f in self.findings)

    @property
    def finding_labels(self) -> tuple[str, ...]:
        return tuple(f"{f.category.value}:{f.detector}" for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        """Audit record. Deliberately excludes the content itself."""

        return {
            "decision": self.decision.value,
            "redacted": self.redacted,
            "original_length": self.original_length,
            "reasons": list(self.reasons),
            "findings": [f.to_dict() for f in self.findings],
            "inspected_at": self.inspected_at.isoformat(),
        }
