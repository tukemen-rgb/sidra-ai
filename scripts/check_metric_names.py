#!/usr/bin/env python3
"""A completion must name a number somebody else can still measure.

C-1893, and the item's own premise was measured before any of this was
written - because it was wrong in the part that mattered.

The filing said six `[x] 完了` records "quote a metric name the repository
no longer has", so they "cannot be re-measured". Read the six completion
lines and none of that holds: all five 09-05/09-06 attract records name
``creation_attract_demo``, the metric the five were consolidated into, and
the sixth names ``creation_draw_request_makes_art``. Both exist. **Zero
completions on this board are unfalsifiable.**

What is actually stale is the *brief* - the 「→ 動かす数字:」 line written
when an item was filed, which still names the pre-consolidation metric. A
brief is a plan, not a claim, and a plan overtaken by a later merge is not
a broken receipt. So the eleven names that resolve nowhere are worth
*printing*, and worth refusing for exactly nobody.

The filing also proposed lifting ``check_backlog_board.MOVES`` to do the
extraction. Measured over the last forty commits that completed an item:
**``MOVES`` matches zero added lines on a completion push.** The 「→ 動かす
数字:」 line lives in the brief and is not re-added when the box is ticked,
so a check built that way could never fire on the case the item exists for
- and a check that cannot fail is not a check.

The receipt is where the claim is. Measured over the last 120 commits that
touched the board, 57 of 57 completion lines carry a backticked identifier,
and in 57 of 57 the *first* one is the metric being claimed - never a test
name, never a script. All 57 resolve today. That property is true and
nothing enforces it, which is what this file is for.

    python scripts/check_metric_names.py

Exit 0 when every completion this push adds names a metric that exists, 1
when one does not, and 0 with a note when git cannot say what is being
pushed - a check that reads nothing must not pass in silence.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BOARD = Path("docs/BACKLOG.md")

#: A completion line, as the board writes it: the receipt goes in front of
#: the title, and the number it claims is the first thing in the bracket.
#:   - [x] 完了 2026-09-16 14:21 UTC 辛口クリエイター（`creation_flash...` 新設 10、...
DONE = re.compile(r"^- \[x\] 完了")

#: A backticked bare identifier. Anchored on both ends so that
#: `verify_gate_recall.py`, `tests/test_product_metrics.py` and `--compare`
#: are not read as metric names - only a bare snake_case word is.
NAME = re.compile(r"`([a-z][a-z0-9_]{6,})`")

#: What counts as "the repository has this name". Deliberately every text
#: kind, not just ``.py``: five of the names the filer first called missing
#: live in other judges (``check_answerable_regression.py``,
#: ``check_boss_questions.py``, ``outcome_questions.py``) and the filer's
#: own first count of 13 was wrong for exactly this reason. **The judge is
#: not one script.**
EXTENSIONS = (".py", ".json", ".md", ".js", ".html", ".txt")

#: The two files that are narrative about the numbers rather than places
#: the numbers live. Counting them would let a name resolve to the very
#: sentence that named it.
NOT_EVIDENCE = frozenset({"docs/BACKLOG.md", "docs/LOOP_LOG.md"})


def _git(*args: str) -> subprocess.CompletedProcess:
    #: C-1976: a combined diff's hunk header carries a line of context -
    #: ``@@@ ... @@@ API 利用者は区別できる。`` - and git cuts it to a byte
    #: length, which lands in the middle of a multi-byte character. The
    #: gate then died reading its own input, on a merge commit, with a
    #: traceback instead of a verdict. The bytes that break are never in a
    #: line this file reads: ``_added_lines`` keeps only ``+`` lines.
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, errors="replace"
    )


def _added_lines(diff: str) -> list[str]:
    return [
        line[1:]
        for line in diff.split("\n")
        if line.startswith("+") and not line.startswith("+++")
    ]


def repository_names(root: Path = Path(".")) -> str:
    """Every tracked text file, as one haystack, minus the two narratives."""

    listed = _git("ls-files")
    if listed.returncode != 0:
        return ""
    out: list[str] = []
    for name in listed.stdout.split("\n"):
        name = name.strip()
        if not name or name in NOT_EVIDENCE or not name.endswith(EXTENSIONS):
            continue
        try:
            out.append((root / name).read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(out)


def claimed_metric(line: str) -> str | None:
    """The number a completion line says it moved, or None.

    The first backticked identifier on the line. Measured over 57 real
    completion lines: it is the claimed metric in every one of them.
    """

    if not DONE.match(line):
        return None
    found = NAME.search(line)
    return found.group(1) if found else None


def unresolved_in_push(haystack: str) -> tuple[list[tuple[str, str, str]], bool]:
    """Each completion this push adds that names a metric the repository
    does not have, as (where, metric, line) - and whether the upstream
    comparison could be read at all."""

    problems: list[tuple[str, str, str]] = []
    listed = _git("rev-list", "origin/main..HEAD")
    shas = (
        [s for s in listed.stdout.split("\n") if s.strip()]
        if listed.returncode == 0
        else []
    )
    diffs = [
        (sha[:8], _git("show", "--format=", "--unified=0", sha, "--", str(BOARD)))
        for sha in shas
    ]
    staged = _git("diff", "--cached", "--unified=0", "--", str(BOARD))
    if staged.returncode == 0:
        diffs.append(("(staged)", staged))
    for where, shown in diffs:
        if shown.returncode != 0:
            continue
        for line in _added_lines(shown.stdout):
            metric = claimed_metric(line)
            if metric and metric not in haystack:
                problems.append((where, metric, line.strip()))
    return problems, listed.returncode == 0


def stale_plans(haystack: str, board: Path = BOARD) -> list[str]:
    """Brief-level 「→ 動かす数字:」 names that resolve nowhere.

    Reported, never refused (禁じ手 ② - stopping on what is already there
    stops everyone for lines nobody can fix). A brief naming a number that
    does not exist yet is also how a *new* metric is proposed: both items
    filed on 2026-09-16 did exactly that, and refusing them would have
    refused the push that claimed this very item.
    """

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_backlog_board import MOVES  # the same rule, not a second copy

    try:
        text = board.read_text(encoding="utf-8")
    except OSError:
        return []
    return sorted({n for n in MOVES.findall(text) if n not in haystack})


def main() -> int:
    haystack = repository_names()
    if not haystack:
        print("NOTE: リポジトリの本文を読めないので指標名を照合していない")
        return 0

    problems, read_upstream = unresolved_in_push(haystack)
    if not read_upstream:
        print("NOTE: origin/main が読めないので push 対象の commit を判定していない")

    # 禁じ手 ② asks for these to be counted and printed, not refused. The
    # count is the report; the names are behind ``--list`` so that the gate
    # a loop reads before every push stays readable. Printed on the way
    # through either way - a NOTE nobody sees is the same as claiming the
    # check looked (C-1723).
    stale = stale_plans(haystack)
    if stale:
        print(
            f"NOTE: 板の「→ 動かす数字:」のうち {len(stale)} 件が repo に無い"
            "（拒否しない——新設の起票と、統合で置き換わった計画行）"
            f"{'' if '--list' in sys.argv else '。名前は --list'}"
        )
        if "--list" in sys.argv:
            for name in stale:
                print(f"      - {name}")

    if problems:
        print("REFUSED: 完了が、repo に無い指標名で「数字が動いた」と主張している")
        for where, metric, line in problems:
            print(f"  - {where}: `{metric}` はリポジトリのどこにも無い")
            print(f"    {line[:100]}")
        print("  直し方: 統合・改名したなら、行き先を一行書いてから push する。")
        return 1

    print("この push が足す完了行は、実在する指標名を名乗っている")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
