"""Does the quarantine triage list say when an entry has more findings than shown?

C-1731. ``sidra-quarantine list`` prints one line per entry ending with up to three
finding labels (``category:detector``) as a triage preview. But it caps at three and
drops the rest silently, so an entry the gate flagged five ways looks the same as one
flagged three - and an operator deciding how much scrutiny to give before a release
under-reads the more dangerous entry. ``show <id>`` lists every finding, but the
triage view should still say how many it hid, the honesty the flat listing (C-1680),
a clipped excerpt (C-1264) and a truncated commit file list (C-1724) already keep.
``summary`` now discloses the remaining count.

The checks build entries with varying finding counts: a >3-finding entry names three
and discloses the remainder, an at-or-under-three entry gets no disclosure, and the
line still carries no detected value.
"""

from __future__ import annotations

from dataclasses import dataclass

_LABELS = [
    ("secret", "token"), ("pii", "email"), ("injection", "override"),
    ("entropy", "high"), ("control", "bytes"), ("cmd", "coerce"),
]


def _summary(n_findings: int) -> str:
    from sidra_ai.security.quarantine_review import QuarantineEntry

    findings = [
        {"category": cat, "detector": det, "severity": "high",
         "reason": "LEAKED_REASON_TEXT"}
        for cat, det in _LABELS[:n_findings]
    ]
    record = {
        "recorded_at": "2026-09-12T00:00:00Z",
        "content_retention": "sanitized",
        "original_length": 100,
        "document_id": "doc1",
        "gate": {"decision": "quarantine", "reasons": ["r"], "findings": findings},
        "provenance": {"repository": "acme/h", "source": "github", "source_type": "docs"},
    }
    return QuarantineEntry.from_record(record).summary()


@dataclass(frozen=True)
class QuarantineFindingCountResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_quarantine_list_discloses_finding_count() -> QuarantineFindingCountResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    five = _summary(5)

    # --- (A) the first three are named and the cap holds (4th not listed) ---
    add("secret:token" in five and "injection:override" in five
        and "entropy:high" not in five,
        f"A: the 3-label cap did not hold (a label missing or the 4th listed): {five!r}")

    # --- (B) the remaining count is disclosed (5 findings, 3 shown -> +2) ---
    add("+2" in five, f"B: the remaining finding count was not disclosed: {five!r}")

    # --- (C) it reads as a remainder, with 'more' ---
    add("more" in five, f"C: the remainder had no 'more' wording: {five!r}")

    # --- (D) an entry at the cap (exactly 3) gets no disclosure ---
    three = _summary(3)
    add("more" not in three and "+" not in three,
        f"D: a 3-finding entry got a spurious remainder: {three!r}")

    # --- (E) a 0-finding entry reads 'no findings', no remainder ---
    zero = _summary(0)
    add("no findings" in zero and "more" not in zero,
        f"E: a 0-finding entry regressed: {zero!r}")

    # --- (F) the line carries no detected value (a finding's reason text) ---
    add("LEAKED_REASON_TEXT" not in five and five.startswith(_summary(5)[:8]),
        f"F: the summary leaked finding reason text: {five!r}")

    total = 6
    return QuarantineFindingCountResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["QuarantineFindingCountResult", "evaluate_quarantine_list_discloses_finding_count"]
