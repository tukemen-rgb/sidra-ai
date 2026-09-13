"""Does `sidra-quarantine list` say it is showing only the pending subset?

C-1743. ``sidra-quarantine list`` (without ``--all``) shows only the *pending*
entries - the actionable set - but its footer prints a bare ``"{N} entries."``.
A reviewer running ``list`` on a log of 5 (2 pending, 3 policy-refusals) sees
"2 entries" with no signal that 3 more exist or that ``--all`` would show them.
The empty case already distinguishes "nothing pending review" from "no entries",
but the non-empty footer is silent about the filter. This is the same honesty a
truncated listing (C-1680), a clipped excerpt (C-1264) and a capped finding count
(C-1731) already keep: say when what is shown is a subset. The footer now names
the pending count, the total, and points to ``--all`` when entries are hidden;
``--all`` and the all-pending case are unchanged.

The checks drive the real CLI over a mixed log: the default footer discloses the
total and ``--all`` and reads as "pending", an all-pending log gets no spurious
"--all" nag, ``--all`` still lists every entry, and the pending filter still hides
policy entries.
"""

from __future__ import annotations

from sidra_ai.evals.scratch import scratch_dir

import contextlib
import io
import json
import os
from dataclasses import dataclass


def _write_log(records: list[dict]) -> str:
    d = scratch_dir()
    log = os.path.join(d, "quarantine.jsonl")
    with open(log, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return log


def _rec(decision: str, repo: str) -> dict:
    return {
        "recorded_at": "2026-09-13T00:00:00Z",
        "content_retention": "sanitized",
        "original_length": 100,
        "document_id": "doc" + repo,
        "gate": {
            "decision": decision,
            "reasons": ["r"],
            "findings": [{"category": "secret", "detector": "token",
                          "severity": "high", "reason": "x"}],
        },
        "provenance": {"repository": repo, "source": "github", "source_type": "docs"},
    }


def _run(argv: list[str]) -> str:
    from sidra_ai.security import quarantine_cli

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        quarantine_cli.main(argv)
    return buf.getvalue()


@dataclass(frozen=True)
class QuarantineListScopeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_quarantine_list_discloses_scope() -> QuarantineListScopeResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A mixed log: 2 pending (quarantine), 3 hidden (block = policy refusal).
    mixed = _write_log([
        _rec("quarantine", "acme/a"), _rec("quarantine", "acme/b"),
        _rec("block", "acme/c"), _rec("block", "acme/d"), _rec("block", "acme/e"),
    ])
    default_out = _run(["--path", mixed, "list"])
    all_out = _run(["--path", mixed, "list", "--all"])

    footer = [ln for ln in default_out.splitlines() if "detail" in ln]
    footer_line = footer[0] if footer else ""

    # --- (A) the default footer reads as the pending subset (names 2, "pending") ---
    add("pending" in footer_line and "2" in footer_line,
        f"A: the default footer did not read as a pending subset: {footer_line!r}")

    # --- (B) it discloses the total (5) when entries are hidden ---
    add("5" in footer_line,
        f"B: the default footer did not disclose the total: {footer_line!r}")

    # --- (C) it points to --all when entries are hidden ---
    add("--all" in footer_line,
        f"C: the default footer did not point to --all: {footer_line!r}")

    # --- (D) --all still lists every entry (no regression) ---
    add("acme/e" in all_out and "5 entries" in all_out,
        f"D: --all did not list all entries")

    # --- (E) an all-pending log gets no spurious total/--all disclosure ---
    all_pending = _write_log([_rec("quarantine", "acme/a"), _rec("quarantine", "acme/b")])
    ap_out = _run(["--path", all_pending, "list"])
    ap_footer = [ln for ln in ap_out.splitlines() if "detail" in ln]
    ap_line = ap_footer[0] if ap_footer else ""
    add("pending" in ap_line and "--all" not in ap_line and "not shown" not in ap_line,
        f"E: an all-pending log over-disclosed: {ap_line!r}")

    # --- (F) the pending filter still hides policy entries in the default view ---
    add("acme/a" in default_out and "acme/c" not in default_out,
        "F: the default view no longer filters to pending")

    total = 6
    return QuarantineListScopeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["QuarantineListScopeResult", "evaluate_quarantine_list_discloses_scope"]
