"""Does the board checker say which 「~」 are live, or only that the board parses?

C-1819: ``check_backlog_board.py`` has been able to name the leftover claims
since C-1728 - ``_stranded_claims`` finds them and ``ACKNOWLEDGED`` says which
ones somebody has already explained - and it printed none of it. Its whole
output was 「761 項目（うち採番 639）・不整合なし」.

Measured 2026-09-14: 22 lines of ``docs/LOOP_LOG.md`` mention C-1694 or C-1699,
**19 of them inside a no-op explanation**, from 09-12 03:22 to 09-14 14:08 -
about 59 hours of three loops re-deriving the same sentence from prose. The
knowledge was there; it had no way out.

The three cases are the ones the item named, and two of them exist to stop the
cheap version of this. A report that simply hid whatever it judged a leftover
would satisfy "says which are live" while making the board *less* readable:

* **A** the output names how many 「~」 there are and splits them;
* **B** a claim with **no written reason** is on the live side however old it
  is - leftover status is the written 「この行は取り残しです」, never the age
  (C-1728's core), so a machine can never retire a claim by judging it;
* **C** a claim judged a leftover is still printed, named as one. Removing it
  from the output would let "solved by becoming invisible" score full marks;
* **D** the age of a live claim is the age of the **commit** that carried the
  line. This is not in the item's A/B/C - it was added because breaking the
  commit lookup moved no number, and 禁じ手 ④ names it explicitly;
* **E** a claim git cannot place - claimed but not yet committed - reads as
  unknown, not as fresh. A loop's own claim is uncommitted for the seconds
  between writing and pushing, and "0 分" there is a guess wearing a number;
* **F** the report still prints when the board is inconsistent. That is the
  moment a reader most wants it, and the failure branch is a separate path.

Driven against a real git checkout, because the age has to come from the commit
that carried the line and not from the timestamp written on it (C-1813 censused
the board's own stamps: 73 of 687 lead their own commit by over 30 minutes,
worst +719).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

#: A board carrying one of each shape. The finished line declares both metrics
#: 新設, so both 「~」 below are *structurally* stranded; only one of them
#: carries the written reason, and that difference is the whole of rule B.
#:
#: The 新設 declaration sits on the heading line, not in the body, because that
#: is where ``_stranded_claims`` reads it and where the two real strandings
#: (C-1694, C-1699) carry it. Writing it in the body made this board parse as
#: three live claims - a probe that reproduced nothing.
#:
#: C-9006 is appended *after* the commit, so git cannot place it: that is the
#: uncommitted case, and rule E is that it reads as unknown rather than fresh.
#:
#: C-9005's own stamp says 09-01 while the commit that carries it is made
#: seconds ago. An age read off the line would be about two weeks; an age read
#: off the commit is minutes. Rule D below is that difference, and without it
#: breaking the commit lookup changed no number here.
_BOARD = """# 盤

### C. 試験用

- [x] 完了 2026-09-13 10:00 UTC ループA（`metric_alpha` **新設 unmeasurable→3**） **C-9001: 済んだ仕事。**
- [~] 作業中 2026-09-13 09:00 UTC ループB **C-9003: 取り残し（理由あり）。**（`metric_alpha` 新設）
      **注（進捗監視）**: この行は取り残しです。採番の付け替えで残ったもの。
- [~] 作業中 2026-09-01 15:00 UTC ループA **C-9005: 本当に作業中。**
      → 動かす数字: `metric_gamma` unmeasurable→1。
"""


#: Appended after the commit, so `git blame` cannot place it.
_UNCOMMITTED = (
    "- [~] 作業中 2026-09-01 16:00 UTC ループA **C-9006: push 前の確保。**\n"
)

#: The rule-B board: a claim whose promised metric is already 新設 on a finished
#: line and which **nobody has explained**. The checker refuses it (that is
#: C-1728 working), so this board also exercises the refusal path - and the
#: claim still has to be listed, on the live side. Committed twice on purpose:
#: a stranding counts only when it survives two versions, so one commit would
#: leave the refusal unarmed and the board would pass for the wrong reason.
_UNEXPLAINED = _BOARD + (
    "- [x] 完了 2026-09-13 11:00 UTC ループA（`metric_beta` **新設 unmeasurable→2**） **C-9002: これも済んだ。**\n"
    "- [~] 作業中 2026-09-13 09:30 UTC ループB **C-9004: 取り残し（理由なし）。**（`metric_beta` 新設）\n"
)


@dataclass(frozen=True)
class BoardClaimsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _run(root: Path, board: Path) -> tuple[list[str], int, str]:
    """Run the real script over ``board``; return its lines and exit code."""

    import sys

    script = Path(__file__).resolve().parents[3] / "scripts" / "check_backlog_board.py"
    ran = subprocess.run(
        [sys.executable, str(script), str(board)],
        capture_output=True, text=True, cwd=root,
    )
    if ran.returncode not in (0, 1):
        return [], ran.returncode, f"the checker crashed: {ran.stderr[:160]}"
    return ran.stdout.split("\n"), ran.returncode, ""


def _report_over_a_real_checkout() -> tuple[list[str], int, list[str], int, str]:
    """Run the real script over two committed boards, or say why not.

    The *script*, as a subprocess, not ``claims_report`` in-process: the whole
    defect was that the knowledge existed and never reached stdout, so a check
    that calls the function directly cannot see it come back. Deleting the
    print from ``main`` left this eval at full marks until it was driven this
    way.

    Two boards because ``main`` has two exits and the report has to come out of
    both. The first is one the checker is happy with; the second carries an
    unexplained stranding, which it refuses.
    """

    from sidra_ai.evals.scratch import scratch_dir

    root = Path(scratch_dir(prefix="board-claims-"))

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)

    for command in (
        ("init", "-q"),
        ("config", "user.email", "probe@example.invalid"),
        ("config", "user.name", "probe"),
    ):
        done = git(*command)
        if done.returncode != 0:
            return [], 0, [], 0, f"throwaway checkout failed at {command[0]}: {done.stderr[:120]}"

    good = root / "BACKLOG.md"
    unexplained = root / "UNEXPLAINED.md"
    good.write_text(_BOARD, encoding="utf-8")
    # Two *different* recorded versions, both carrying the stranding: the
    # refusal only fires when a claim is stranded in this board and the one
    # before it (C-1728 measured that a single version is somebody mid-edit).
    # An --allow-empty second commit does not give the file a second version,
    # which left this board passing for the wrong reason.
    unexplained.write_text(_UNEXPLAINED + "\n<!-- 第1版 -->\n", encoding="utf-8")
    for text_now, message in ((None, "board"), (_UNEXPLAINED, "board again")):
        if text_now is not None:
            unexplained.write_text(text_now, encoding="utf-8")
        git("add", "-A")
        done = git("commit", "-q", "-m", message)
        if done.returncode != 0:
            return [], 0, [], 0, f"throwaway commit failed: {done.stderr[:120]}"

    # ...and now a claim that is written but not yet committed.
    good.write_text(_BOARD + _UNCOMMITTED, encoding="utf-8")

    good_lines, good_code, problem = _run(root, good)
    if problem:
        return [], 0, [], 0, problem
    bad_lines, bad_code, problem = _run(root, unexplained)
    if problem:
        return [], 0, [], 0, problem
    return good_lines, good_code, bad_lines, bad_code, ""


def _sections(lines: list[str]) -> tuple[list[str], list[str]]:
    """The live entries and the leftover entries, as printed.

    Read by walking the two headings rather than by splitting the whole of
    stdout: the refusal message quotes the very ids being judged, so a
    substring test over the blob found 「C-9004」 in the complaint and called
    the rule satisfied while the entry had moved to the other list.
    """

    live: list[str] = []
    left: list[str] = []
    into: list[str] | None = None
    for row in lines:
        if row.startswith("  生きている:"):
            into = live
        elif row.startswith("  取り残し（"):
            into = left
        elif row.startswith("    ") and into is not None:
            into.append(row)
        elif not row.startswith(" "):
            into = None
    return live, left


def evaluate_board_says_which_claims_are_live() -> BoardClaimsResult:
    report, good_code, unexplained, bad_code, problem = _report_over_a_real_checkout()
    if problem:
        return BoardClaimsResult(False, 0, 7, (problem,))
    text = "\n".join(report)
    other = "\n".join(unexplained)
    live_rows, left_rows = _sections(report)
    other_live, other_left = _sections(unexplained)

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A: the counts, and every 「~」 accounted for.
    counted = "確保「~」3 件: 生きている 2 件・取り残し 1 件" in text
    listed = {n for n in (3, 5, 6)
              if any(f"C-900{n}" in row for row in live_rows + left_rows)}
    add(
        counted and listed == {3, 5, 6},
        f"the report does not count and name every 「~」 (listed {sorted(listed)}): "
        f"「{text[:140]}」",
    )

    # B: the unexplained stranding is live, and the explained one is not.
    add(
        any("C-9004" in row for row in other_live)
        and not any("C-9004" in row for row in other_left)
        and any("C-9003" in row for row in other_left),
        "a claim with no written reason was retired by the machine, or a "
        f"written leftover was called live: 生きている={other_live} 取り残し={other_left}",
    )

    # C: the explained leftover is still printed, named as one.
    add(
        any("C-9003" in row for row in left_rows),
        f"a claim judged a leftover vanished from the report: 取り残し={left_rows}",
    )

    # D: the age is the commit's, not the line's. C-9005's line says 09-01 and
    # its commit was made seconds ago, so a line-derived age reads in days.
    live_line = next((row for row in live_rows if "C-9005" in row), "")
    add(
        "確保から" in live_line and "日" not in live_line and "時間" not in live_line,
        "the age looks like it came from the board's own stamp rather than the "
        f"commit that carried the line: 「{live_line.strip()}」",
    )

    # E: a claim git cannot place reads as unknown, not as freshly made.
    pending = next((row for row in live_rows if "C-9006" in row), "")
    add(
        "経過不明" in pending,
        f"an uncommitted claim was given an age instead of 「経過不明」: 「{pending.strip()}」",
    )

    # F: the report comes out of both exits - the happy one...
    add(
        good_code == 0 and "確保「~」" in text,
        f"the claim report is missing from the success path (exit {good_code}): "
        f"「{text[:120]}」",
    )
    # ...and the refusal, which is when a reader wants it most.
    add(
        bad_code == 1 and "確保「~」" in other,
        f"the claim report vanished on a refused board (exit {bad_code}): "
        f"「{other[:160]}」",
    )

    return BoardClaimsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=7,
        failures=tuple(failures),
    )


__all__ = ["BoardClaimsResult", "evaluate_board_says_which_claims_are_live"]
