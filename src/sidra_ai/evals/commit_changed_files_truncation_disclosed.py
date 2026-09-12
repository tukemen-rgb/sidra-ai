"""Does an indexed commit say when its changed-file list was truncated?

C-1724. ``commit_document`` appends 「changed files: …」 to a commit's indexed
content, but caps the list at the first 20 files and drops the rest silently. A
refactor or merge touching 50 files is indexed as if it changed exactly the 20
that happened to sort first, and a reader who asks 「what did this commit change」
is handed an incomplete list with no sign it was cut - the same silent-truncation
the product refuses elsewhere (C-1680 reports the true total, C-1264 marks a cut
excerpt with 「…」). ``commit_document`` now discloses how many more files there
were.

The checks drive ``commit_document``: a >20-file commit names the first 20, marks
the cut and states the remaining count, still does not list the 21st file (the cap
holds), and a commit at or under the cap gets no truncation note.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _commit(n_files: int):
    from sidra_ai.ingestion.normalize import commit_document

    payload = {
        "sha": "a" * 40,
        "commit": {
            "message": "big refactor",
            "author": {"date": "2026-01-01T00:00:00Z", "name": "Dev"},
        },
        "files": [{"filename": f"src/module_{i}.py"} for i in range(n_files)],
    }
    doc = commit_document(payload, repository="acme/h", license="MIT")
    assert doc is not None
    return doc.content


@dataclass(frozen=True)
class CommitTruncationResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_commit_changed_files_truncation_disclosed() -> CommitTruncationResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    big = _commit(50)

    # --- (A) the first 20 files are still named ---
    add("src/module_0.py" in big and "src/module_19.py" in big,
        f"A: the first 20 changed files were not named: {big[-120:]!r}")

    # --- (B) the cut is marked ---
    add("more" in big, f"B: the truncation was not marked: {big[-120:]!r}")

    # --- (C) the remaining count is stated (50 - 20 = 30) ---
    add("30 more" in big, f"C: the remaining count was wrong or absent: {big[-120:]!r}")

    # --- (D) the cap still holds: the 21st+ file is not individually named ---
    add("src/module_25.py" not in big and "src/module_49.py" not in big,
        f"D: the cap no longer holds (a beyond-20 file was listed): {big[-160:]!r}")

    # --- (E) a commit at the cap (exactly 20) gets no truncation note ---
    at_cap = _commit(20)
    add("more" not in at_cap, f"E: a 20-file commit got a spurious truncation note: {at_cap[-100:]!r}")

    # --- (F) a small commit is unchanged and the message survives ---
    small = _commit(3)
    add("big refactor" in small and "more" not in small
        and "src/module_2.py" in small,
        f"F: a small commit regressed: {small!r}")

    total = 6
    return CommitTruncationResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CommitTruncationResult", "evaluate_commit_changed_files_truncation_disclosed"]
