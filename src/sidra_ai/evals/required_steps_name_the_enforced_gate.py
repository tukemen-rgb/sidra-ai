"""Does 「検証（省略不可）」 name the check that actually fails the build?

C-1824: the section told a loop that touched a detector to re-measure the
false-positive rate with ``measure_gate_baseline.py`` and compare against
「現在の基準値は 1012 文書中 3.5%」. Two things were wrong with that as an
instruction:

* the check that actually stops a bad change is ``check_gate_regression.py``,
  which CI runs every time (``.github/workflows/integration-v01.yml`` L154) and
  which enforces ``MAX_FLAG_RATE`` and ``MAX_FILE_FLAG_RATE`` mechanically. Its
  name appeared nowhere in the section - the same shape as C-1807, where the
  push gate was missing from 手順 0;
* the 3.5% was called 「現在の基準値」 while being a 2026-08-18 reading of a
  corpus that has since grown by a factor of two and a half.

The item filed a third claim - that the procedure cannot be run in this
container because only ``sidra-ai`` is checked out - and **that one is false**:
all four other repositories are present under ``/workspace/tukemen-rgb/``, and
running the procedure as written gives 2521 documents at 5.7%. So the fix is
not "say it cannot be measured here"; it is to measure it and date both
readings. Rule C below is written against the doc for that reason.

Each rule is measured by doctoring a copy of the file and checking the rule
goes to 0 - a rule that cannot fail is not a rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: The section this item is about, and the file that carries the readings.
_BOARD = Path("docs/BACKLOG.md")
_BASELINE = Path("docs/GATE_FALSE_POSITIVE_BASELINE.md")

#: The gate that actually fails a build, and its two ceilings as CI holds them.
_ENFORCED = "check_gate_regression.py"
_CEILINGS = ("13.0%", "20.0%")

#: What the 3.5% must no longer be called. The number itself is a real
#: measurement and is never deleted (禁じ手 ①); only the claim that it is
#: current is refused.
_STALE_CLAIM = re.compile(r"現在の基準値")


@dataclass(frozen=True)
class RequiredStepsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _section(board_text: str) -> str:
    """The 「検証（省略不可）」 section, heading to next heading."""

    start = board_text.find("## 検証（省略不可）")
    if start == -1:
        return ""
    after = board_text.find("\n## ", start + 1)
    return board_text[start:after if after != -1 else len(board_text)]


def evaluate_required_steps_name_the_enforced_gate(
    board: str | None = None, baseline: str | None = None
) -> RequiredStepsResult:
    """Judge the live documents, or the text handed in.

    The metric reads the real files - the point is whether *this* procedure
    names the gate. The overrides exist so a probe can doctor a copy and show
    each rule going to 0 without editing the board every loop reads.
    """

    root = _root()
    if board is None:
        board = (root / _BOARD).read_text(encoding="utf-8")
    if baseline is None:
        baseline = (root / _BASELINE).read_text(encoding="utf-8")
    section = _section(board)

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A: the section names the check that actually fails.
    add(
        _ENFORCED in section,
        f"「検証（省略不可）」 does not name {_ENFORCED}, the check CI enforces",
    )

    # B: and carries the ceilings it enforces, so raising one quietly shows up
    # here as a disagreement between the gate and the procedure.
    missing = [value for value in _CEILINGS if value not in section]
    add(
        not missing,
        f"the section does not carry the enforced ceilings {missing}",
    )

    # C: the 2026-08-18 reading is kept, and no longer called the current one.
    # Both halves: deleting it would also satisfy "not called current", and
    # deleting a real measurement is 禁じ手 ①.
    kept = "3.5%" in baseline or "3.5%" in section
    add(
        kept and not _STALE_CLAIM.search(section) and not _STALE_CLAIM.search(baseline),
        "the 2026-08-18 reading is either gone (it is a real measurement and "
        f"must stay) or still called 「現在の基準値」: kept={kept}",
    )

    return RequiredStepsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=3,
        failures=tuple(failures),
    )


__all__ = ["RequiredStepsResult", "evaluate_required_steps_name_the_enforced_gate"]
