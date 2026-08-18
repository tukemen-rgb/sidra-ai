"""Human review and release of quarantined content.

The gate quarantines rather than deletes, which is only meaningful if someone
can eventually look at what it held and decide. Without this, quarantine is a
one-way sink: content accumulates, nobody can act on it, and the "we never
delete anything" promise quietly becomes "we lose it more slowly".

Three rules shape the design.

**Only QUARANTINE is reviewable.** ``BLOCK`` is a policy refusal - an
unpermitted source, an oversized input - not a judgement call awaiting a
second opinion. Offering to release it would turn a boundary into a
suggestion.

**Release records a decision; it does not re-index.** This module appends an
approval with an operator and a reason. Acting on it is the ingestion side's
job. Keeping the two apart means a release can be audited, revoked, or simply
never acted on, and nothing indexes itself because a file was edited.

**A reason is required.** An approval trail that records who but not why
cannot be reviewed later, which defeats the point of keeping one.

Note on what a reviewer can see: the audit boundary in
:class:`~sidra_ai.security.gate.QuarantineStore` deliberately drops the path,
URL and author of quarantined items, since those are attacker-controlled and
never passed through the detectors. A reviewer therefore identifies an entry
by its repository, source type, findings, and redacted content - not by its
filename.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

RELEASE_LOG_SUFFIX = ".releases.jsonl"


class NotReleasableError(RuntimeError):
    """Raised when an entry is not a candidate for human release."""


class EntryNotFoundError(KeyError):
    """Raised when no quarantine entry matches the given id."""


def entry_id(record: dict[str, Any]) -> str:
    """Stable id for a quarantine record.

    Derived from the record itself rather than its position, so ids survive
    the log being appended to, and two reviewers naming "entry a3f19c2b" mean
    the same thing.
    """

    canonical = json.dumps(record, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class QuarantineEntry:
    """One quarantined item, as a reviewer sees it."""

    id: str
    recorded_at: str
    decision: str
    repository: str
    source: str
    source_type: str
    reasons: tuple[str, ...]
    findings: tuple[dict[str, Any], ...]
    content_retention: str
    original_length: int
    document_id: str = ""
    """Hash over repository, path, commit and content. Reveals none of them,
    and is recomputable at the next ingestion - which is what makes a release
    actionable, since the audit record deliberately keeps nothing else that
    could identify the document."""

    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def releasable(self) -> bool:
        """Only a quarantine decision is a candidate for human release."""

        return self.decision == "quarantine"

    @property
    def has_content(self) -> bool:
        return self.content_retention == "sanitized" and self.raw.get("content")

    @property
    def finding_labels(self) -> tuple[str, ...]:
        return tuple(
            f"{f.get('category', '?')}:{f.get('detector', '?')}" for f in self.findings
        )

    def summary(self) -> str:
        """One line, safe to print. Carries no detected value."""

        where = self.repository or "(repository withheld)"
        labels = ", ".join(self.finding_labels[:3]) or "no findings"
        return (
            f"{self.id}  {self.recorded_at[:16]}  {self.decision:10s} "
            f"{where:26s} {self.source_type:12s} {labels}"
        )

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "QuarantineEntry":
        gate = record.get("gate") or {}
        provenance = record.get("provenance") or {}
        return cls(
            id=entry_id(record),
            recorded_at=str(record.get("recorded_at", "")),
            decision=str(gate.get("decision", "")),
            repository=str(provenance.get("repository", "")),
            source=str(provenance.get("source", "")),
            source_type=str(provenance.get("source_type", "")),
            reasons=tuple(gate.get("reasons") or ()),
            findings=tuple(gate.get("findings") or ()),
            content_retention=str(record.get("content_retention", "")),
            original_length=int(record.get("original_length") or 0),
            document_id=str(record.get("document_id") or ""),
            raw=record,
        )


@dataclass(frozen=True)
class Release:
    """A recorded human approval."""

    entry_id: str
    operator: str
    reason: str
    released_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "operator": self.operator,
            "reason": self.reason,
            "released_at": self.released_at,
        }


class QuarantineReview:
    """Read a quarantine log and record release approvals against it."""

    def __init__(self, quarantine_path: str | os.PathLike[str]) -> None:
        self.quarantine_path = Path(quarantine_path)
        self.release_path = Path(str(self.quarantine_path) + RELEASE_LOG_SUFFIX)

    # ------------------------------------------------------------------
    def _records(self) -> list[dict[str, Any]]:
        if not self.quarantine_path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.quarantine_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    # A torn final line must not hide every entry before it.
                    continue
        return records

    def entries(self) -> list[QuarantineEntry]:
        return [QuarantineEntry.from_record(r) for r in self._records()]

    def get(self, entry_ref: str) -> QuarantineEntry:
        """Look up by full id or unambiguous prefix."""

        matches = [e for e in self.entries() if e.id.startswith(entry_ref)]
        if not matches:
            raise EntryNotFoundError(f"no quarantine entry matching {entry_ref!r}")
        if len(matches) > 1:
            raise EntryNotFoundError(
                f"{entry_ref!r} matches {len(matches)} entries; use more characters"
            )
        return matches[0]

    # ------------------------------------------------------------------
    def releases(self) -> list[Release]:
        if not self.release_path.exists():
            return []
        out: list[Release] = []
        with self.release_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                out.append(
                    Release(
                        entry_id=str(data.get("entry_id", "")),
                        operator=str(data.get("operator", "")),
                        reason=str(data.get("reason", "")),
                        released_at=str(data.get("released_at", "")),
                    )
                )
        return out

    def released_ids(self) -> set[str]:
        return {r.entry_id for r in self.releases()}

    def released_document_ids(self) -> set[str]:
        """Document ids a human approved, for the gate to admit on re-ingest.

        Pass this to ``SecurityGate(released_document_ids=...)``. Entries
        recorded before document ids were kept have none, and are skipped
        rather than guessed - an approval that cannot be tied to a specific
        document is not an approval of anything.
        """

        approved = self.released_ids()
        return {
            entry.document_id
            for entry in self.entries()
            if entry.document_id and entry.id in approved
        }

    def pending(self) -> list[QuarantineEntry]:
        """Releasable entries a human has not yet acted on."""

        done = self.released_ids()
        return [e for e in self.entries() if e.releasable and e.id not in done]

    # ------------------------------------------------------------------
    def release(self, entry_ref: str, *, operator: str, reason: str) -> Release:
        """Record a human approval. Raises rather than approving silently."""

        operator = operator.strip()
        reason = reason.strip()
        if not operator:
            raise ValueError("an operator is required: a release needs an owner")
        if len(reason) < 8:
            raise ValueError(
                "a reason of at least 8 characters is required: an approval "
                "trail without a why cannot be reviewed later"
            )

        entry = self.get(entry_ref)
        if not entry.releasable:
            raise NotReleasableError(
                f"entry {entry.id} was {entry.decision!r}, not quarantined. A "
                "policy refusal is not a judgement call awaiting a second "
                "opinion and cannot be released here"
            )
        if entry.id in self.released_ids():
            raise NotReleasableError(f"entry {entry.id} was already released")

        release = Release(
            entry_id=entry.id,
            operator=operator,
            reason=reason,
            released_at=datetime.now(timezone.utc).isoformat(),
        )
        self._append_release(release)
        return release

    def _append_release(self, release: Release) -> None:
        self.release_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.release_path.exists():
            self.release_path.touch(mode=0o600)
        else:
            os.chmod(self.release_path, 0o600)
        with self.release_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(release.to_dict(), ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        entries = self.entries()
        by_decision: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for entry in entries:
            by_decision[entry.decision] = by_decision.get(entry.decision, 0) + 1
            for finding in entry.findings:
                key = str(finding.get("category", "?"))
                by_category[key] = by_category.get(key, 0) + 1
        return {
            "total": len(entries),
            "releasable": sum(1 for e in entries if e.releasable),
            "released": len(self.released_ids()),
            "pending": len(self.pending()),
            "by_decision": by_decision,
            "by_finding_category": by_category,
        }


def released_entries(
    review: QuarantineReview, entries: Iterable[QuarantineEntry] | None = None
) -> Sequence[QuarantineEntry]:
    """Entries a human approved, for an ingestion side that wants to act."""

    done = review.released_ids()
    source = list(entries) if entries is not None else review.entries()
    return [e for e in source if e.id in done]
