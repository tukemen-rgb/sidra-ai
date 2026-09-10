"""Does the artifacts/projects listing really order newest-first?

C-1641. Both listings promise "Newest first" (``artifacts.py`` docstrings),
but they sorted on ``modified`` - the timestamp already truncated to whole
seconds for display. Sub-second recency was thrown away, so two files written
in the same wall-clock second (the common case: the echo model generates
instantly, and an operator runs 「作って」 several times in a session) fell
back to the name tiebreaker. With ``reverse=True`` that tiebreak is name
*descending*, which reverses recency: the file just made can land at the
bottom if its name sorts low.

The checks drive the real ``list_artifacts`` / ``list_projects`` with
``os.utime`` to force three entries into one integer second, in a definite
sub-second order whose names are the exact reverse of that order, and assert
the listing comes back in true-recency order - while the displayed
``modified`` string stays second-resolution and the within-project files stay
name-ascending. A genuine tie (identical mtime) must still fall back to the
name tiebreak, and an empty directory must still be an empty list.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass


def _names(entries) -> list[str]:
    return [e.name for e in entries]


@dataclass(frozen=True)
class ListingNewestFirstResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_artifacts_listing_newest_first() -> ListingNewestFirstResult:
    from sidra_ai.api.artifacts import (
        artifacts_dir,
        list_artifacts,
        list_projects,
        projects_dir,
    )

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- flat artifacts listing ---
    d = tempfile.mkdtemp()
    adir = artifacts_dir(d)
    adir.mkdir(parents=True)
    # Same integer second (1000.x). Sub-second order = recency; names are its
    # exact reverse, so a name tiebreak would invert the result.
    plan = [("z-oldest.md", 1000.10), ("m-middle.md", 1000.50), ("a-newest.md", 1000.90)]
    for name, mtime in plan:
        p = adir / name
        p.write_bytes(b"x")
        os.utime(p, (mtime, mtime))
    listed = list_artifacts(d)
    true_recency = ["a-newest.md", "m-middle.md", "z-oldest.md"]
    add(_names(listed) == true_recency,
        f"artifacts same-second order not newest-first: {_names(listed)}")
    add(bool(listed) and listed[0].name == "a-newest.md",
        f"artifacts head is not the newest file: {_names(listed)[:1]}")
    # Display stays second-resolution (fix must not leak sub-second into output).
    add(bool(listed) and listed[0].modified.endswith("Z") and "." not in listed[0].modified,
        f"artifacts modified is not whole-second: "
        f"{listed[0].modified if listed else None!r}")

    # cross-second: a later second always precedes an earlier one, name aside.
    d2 = tempfile.mkdtemp()
    adir2 = artifacts_dir(d2)
    adir2.mkdir(parents=True)
    (adir2 / "aaa.md").write_bytes(b"x")
    os.utime(adir2 / "aaa.md", (5000.0, 5000.0))   # newer second, low name
    (adir2 / "zzz.md").write_bytes(b"x")
    os.utime(adir2 / "zzz.md", (4000.0, 4000.0))   # older second, high name
    listed2 = list_artifacts(d2)
    add(_names(listed2) == ["aaa.md", "zzz.md"],
        f"artifacts cross-second order wrong: {_names(listed2)}")

    # genuine tie (identical mtime) keeps the name-descending tiebreak.
    d3 = tempfile.mkdtemp()
    adir3 = artifacts_dir(d3)
    adir3.mkdir(parents=True)
    for name in ("apple.md", "mango.md", "zebra.md"):
        p = adir3 / name
        p.write_bytes(b"x")
        os.utime(p, (7000.0, 7000.0))
    listed3 = list_artifacts(d3)
    add(_names(listed3) == ["zebra.md", "mango.md", "apple.md"],
        f"artifacts tie tiebreak not name-descending: {_names(listed3)}")

    # empty directory -> empty list.
    add(list_artifacts(tempfile.mkdtemp()) == [],
        "artifacts empty dir not []")

    # --- projects listing ---
    pd = tempfile.mkdtemp()
    pdir = projects_dir(pd)
    pdir.mkdir(parents=True)
    pplan = [("z-old", 2000.10), ("m-mid", 2000.50), ("a-new", 2000.90)]
    for slug, mtime in pplan:
        (pdir / slug).mkdir()
        # Two files per project with names in reverse-recency to also probe the
        # within-project ordering contract (name-ascending, unchanged).
        (pdir / slug / "scenario.md").write_bytes(b"x")
        (pdir / slug / "assets").mkdir()
        (pdir / slug / "assets" / "art.svg").write_bytes(b"x")
        os.utime(pdir / slug, (mtime, mtime))
    projects = list_projects(pd)
    add([p.slug for p in projects] == ["a-new", "m-mid", "z-old"],
        f"projects same-second order not newest-first: {[p.slug for p in projects]}")
    add(bool(projects) and projects[0].slug == "a-new",
        f"projects head is not the newest: {[p.slug for p in projects][:1]}")
    add(bool(projects) and projects[0].modified.endswith("Z")
        and "." not in projects[0].modified,
        f"projects modified is not whole-second: "
        f"{projects[0].modified if projects else None!r}")
    # within-project files stay name-ascending (design contract, must not move).
    if projects:
        files = [a.name for a in projects[0].files]
        add(files == sorted(files),
            f"project files no longer name-ascending: {files}")
    else:
        add(False, "projects listing empty")

    # projects cross-second.
    pd2 = tempfile.mkdtemp()
    pdir2 = projects_dir(pd2)
    pdir2.mkdir(parents=True)
    for slug, mtime in (("aaa", 9000.0), ("zzz", 8000.0)):
        (pdir2 / slug).mkdir()
        (pdir2 / slug / "scenario.md").write_bytes(b"x")
        os.utime(pdir2 / slug, (mtime, mtime))
    projects2 = list_projects(pd2)
    add([p.slug for p in projects2] == ["aaa", "zzz"],
        f"projects cross-second order wrong: {[p.slug for p in projects2]}")

    add(list_projects(tempfile.mkdtemp()) == [],
        "projects empty dir not []")

    total = 12
    return ListingNewestFirstResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ListingNewestFirstResult",
    "evaluate_artifacts_listing_newest_first",
]
