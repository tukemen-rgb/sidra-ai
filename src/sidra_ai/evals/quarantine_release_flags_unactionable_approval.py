"""Does ``sidra-quarantine release`` flag an approval that cannot be acted on?

C-1663. ``QuarantineReview.released_document_ids`` - the set the gate consults
to admit content on re-ingest - keeps only approvals whose entry carries a
``document_id``: "an approval that cannot be tied to a specific document is not
an approval of anything." Entries recorded before document ids were kept have
none. ``release`` records the approval either way and the CLI printed the same
success ("...Re-indexing is a separate, deliberate step on the ingestion
side."), so an operator who releases such a legacy entry is told re-ingestion
will act on it when it silently never can. The CLI now records the approval
(auditing is preserved) but says, for a document-id-less entry, that it cannot
be admitted automatically.

The checks drive the real CLI over a temp log with one modern entry (has a
document id) and one legacy entry (none): the modern release shows the
"separate step" note and no warning; the legacy release still exits 0 and is
recorded, but warns and drops the misleading note. A control check confirms the
warning matches reality - only the modern id is in ``released_document_ids``.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

_MODERN = {
    "recorded_at": "2026-09-01T10:00:00+00:00",
    "gate": {
        "decision": "quarantine",
        "reasons": ["prompt-injection patterns detected"],
        "findings": [{"severity": "high", "category": "injection", "detector": "imperative_override", "reason": "x"}],
    },
    "provenance": {"repository": "tukemen-rgb/site", "source": "", "source_type": "markdown"},
    "content_retention": "sanitized",
    "original_length": 1200,
    "document_id": "abc123def456",
    "content": "do the thing",
}
_LEGACY = {  # recorded before document ids were kept: no document_id
    "recorded_at": "2026-08-01T09:00:00+00:00",
    "gate": {
        "decision": "quarantine",
        "reasons": ["secret-like high entropy"],
        "findings": [{"severity": "medium", "category": "secret", "detector": "high_entropy", "reason": "y"}],
    },
    "provenance": {"repository": "tukemen-rgb/old", "source": "", "source_type": "markdown"},
    "content_retention": "sanitized",
    "original_length": 300,
    "content": "legacy body",
}

_ACTIONABLE_NOTE = "Re-indexing is a separate"


def _write_log() -> Path:
    d = Path(tempfile.mkdtemp())
    log = d / "quarantine.jsonl"
    log.write_text(
        "\n".join(json.dumps(r) for r in (_MODERN, _LEGACY)) + "\n", encoding="utf-8"
    )
    return log


def _release(log: Path, entry_id: str):
    from sidra_ai.security import quarantine_cli

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = quarantine_cli.main(
            ["--path", str(log), "release", entry_id,
             "--operator", "reviewer", "--reason", "reviewed and safe"]
        )
    return code, out.getvalue(), err.getvalue()


@dataclass(frozen=True)
class ReleaseFlagResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_quarantine_release_flags_unactionable_approval() -> ReleaseFlagResult:
    from sidra_ai.security.quarantine_review import QuarantineReview

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    log = _write_log()
    review = QuarantineReview(log)
    by_repo = {e.repository: e for e in review.entries()}
    modern_id = by_repo["tukemen-rgb/site"].id
    legacy_id = by_repo["tukemen-rgb/old"].id

    # --- modern entry: shown as actionable, no unactionable warning ---
    code, out, err = _release(log, modern_id)
    text = out + err
    add(code == 0, f"modern: exit {code}, expected 0")
    add("released" in out, f"modern: no success line: {out!r}")
    add(_ACTIONABLE_NOTE in out, f"modern: the 'separate step' note is missing: {out!r}")
    add(
        "document id" not in text and "通さない" not in text,
        f"modern: warned about an entry that has a document id: {text!r}",
    )

    # --- legacy entry: still recorded (audit), but flagged as unactionable ---
    code, out, err = _release(log, legacy_id)
    text = out + err
    add(code == 0, f"legacy: exit {code}, expected 0 (approval still recorded)")
    add(
        "document id" in text and "通さない" in text,
        f"legacy: not warned that the approval cannot be acted on: {text!r}",
    )
    add(
        _ACTIONABLE_NOTE not in text,
        f"legacy: still shows the misleading 'separate step' note: {text!r}",
    )

    # --- both approvals recorded; only the modern one is actionable ---
    released = review.released_ids()
    add(modern_id in released and legacy_id in released,
        f"both releases must be recorded for audit: {released}")
    actionable = review.released_document_ids()
    add("abc123def456" in actionable,
        f"modern document id should be admittable: {actionable}")
    add(len(actionable) == 1,
        f"legacy approval must not become admittable (no document id): {actionable}")

    total = 10
    return ReleaseFlagResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ReleaseFlagResult",
    "evaluate_quarantine_release_flags_unactionable_approval",
]
