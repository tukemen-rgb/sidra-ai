"""Reviewer's tool: a log line must not claim a time it has not reached.

`docs/LOOP_LOG.md` is read top to bottom as a history, and the timestamp at
the head of each line is what a reader uses to order events. Measured
2026-09-12 over the whole file with `git blame --line-porcelain` - 1818
timestamped lines, not a sample:

* 95.3% of lines are within +5 minutes of the commit that added them
  (median -0.6, p90 +1.6).
* The tail is long: p98 +37.7, p99 +175.6, worst +702.6 minutes - 11.7
  hours in the future.
* 86 lines (4%) are more than +5 minutes ahead, 68 of them from one loop,
  whose lead grew monotonically through the day (+647 -> +703).
* Reading order steps *backwards* at 129 of 1817 adjacent pairs, so the
  file disagrees with itself about what happened first. On 2026-09-12 the
  board carried completion lines dated 2026-09-13 above lines dated 09-12.

The cost is already being paid elsewhere: the stall watch gave up on the
times the lines claim and counts commit times instead, because a claim line
can lead by 150 minutes and cross a date boundary. One instrument lying has
meant using a second instrument.

What this refuses is narrow on purpose:

* Only the lines a push *adds* to the log. The 86 already in the file would
  make every loop red on the first run, which is the trap C-1728 walked
  into; history is left exactly as it is.
* A margin of 30 minutes. The honest lag is real - a loop writes its line
  at the head of a cycle and commits after the work - and measured, the
  honest worst cases are ループA +20.2, ループB +18.5 and 進捗監視 +17.6.
  30 clears all three and still catches everything from p98 (+37.7) up.
  (The item proposing this put the honest maximum at +17.6; the census says
  +20.2. The margin was chosen against the measurement, not the proposal.)

    python scripts/check_log_times.py

Exit 0 when every line a push adds is honest about its own time, 1 when one
is not, and 0 with a note when git cannot say what is being pushed - a
check that reads nothing must not pass in silence about something else.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

LOG = Path("docs/LOOP_LOG.md")

#: The board claims times too, and nothing was checking them (C-1813).
#: Census 2026-09-14 with `git blame --line-porcelain` over every timestamped
#: line of the board - 687 lines, not a sample: **73 (10.6%) lead their own
#: commit by more than 30 minutes**, median +83, worst +719 (about 12 hours),
#: spread over ten days up to that morning. A live one that day claimed
#: 13:4x for a line committed at 09:01.
#:
#: It is not a cosmetic lie. The stall watch reads the time on a `[~]` line to
#: decide whether an item has been sitting; a claim line hours ahead looks like
#: work that has not started, so a stalled item never rings. That watch had
#: already given up and switched to commit times - one instrument lying has
#: meant using a second instrument, which is the same cost C-1733 recorded.
BOARD = Path("docs/BACKLOG.md")

#: Every file whose added lines are judged. LOOP_LOG's behaviour is unchanged.
FILES = (LOG, BOARD)

#: The stamp a log line leads with: 「2026-09-12 20:07 UTC ループA …」.
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*UTC")

#: The board writes its stamp after the box and a word: 「- [~] 作業中
#: 2026-09-14 13:4x UTC ループA」, 「- [x] 完了 …」, 「- [記録] 実測 …」.
#: Only item headings are read - the body quotes measurement times
#: (「実測（2026-09-14 08:2x UTC…」), which are facts about when something was
#: measured, not claims about when the line was written.
BOARD_STAMP = re.compile(
    r"^- \[(?: |x|~|記録)\]\s*\S{0,6}\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:[\dx]{2})\s*UTC"
)

#: Minutes a line may lead the commit that carries it. See the docstring:
#: measured honest lag tops out at +20.2, p98 of the whole file is +37.7.
MARGIN_MINUTES = 30


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _added_lines(diff: str) -> list[str]:
    return [
        line[1:]
        for line in diff.split("\n")
        if line.startswith("+") and not line.startswith("+++")
    ]


def _claimed(line: str, board: bool = False) -> dt.datetime | None:
    found = (BOARD_STAMP if board else STAMP).match(line.strip() if not board else line)
    if not found:
        return None
    # 「13:4x」 hides the minute. Read the `x` as 0 - the EARLIEST minute that
    # spelling can mean - so the lead this reports is a lower bound and the
    # rounding never works in the check's favour. It is also the commonest
    # spelling on the board, so refusing to parse it would skip most of it.
    minute = found.group(2).replace("x", "0")
    return dt.datetime.strptime(
        f"{found.group(1)} {minute}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=dt.timezone.utc)


def _late_lines(
    lines: list[str], made: dt.datetime, board: bool = False
) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for line in lines:
        claimed = _claimed(line, board=board)
        if claimed is None:
            continue
        ahead = (claimed - made).total_seconds() / 60
        if ahead > MARGIN_MINUTES:
            out.append((ahead, line.strip()))
    return out


def check() -> tuple[list[str], list[str]]:
    """Problems, and notes about what could not be read."""

    problems: list[str] = []
    notes: list[str] = []

    # What is about to be pushed. Each commit is judged against its own
    # time, because that is the moment the line entered the history.
    listed = _git("rev-list", "origin/main..HEAD")
    if listed.returncode != 0:
        notes.append(
            "origin/main が読めないので push 対象の commit を判定していない"
        )
    else:
        for sha in [s for s in listed.stdout.split("\n") if s.strip()]:
            stamped = _git("show", "-s", "--format=%ct", sha)
            if stamped.returncode != 0:
                notes.append(f"{sha[:8]} を読めない")
                continue
            made = dt.datetime.fromtimestamp(int(stamped.stdout.strip()), dt.timezone.utc)
            for path in FILES:
                shown = _git("show", "--format=", "--unified=0", sha, "--", str(path))
                if shown.returncode != 0:
                    notes.append(f"{sha[:8]} の {path} を読めない")
                    continue
                for ahead, line in _late_lines(
                    _added_lines(shown.stdout), made, board=path == BOARD
                ):
                    problems.append(
                        f"{sha[:8]} {path}: この行は commit の {ahead:+.0f} 分先を"
                        f"名乗っている（許容 {MARGIN_MINUTES} 分）: {line[:80]}"
                    )

    # And anything staged but not yet committed, against now.
    now = dt.datetime.now(dt.timezone.utc)
    for path in FILES:
        staged = _git("diff", "--cached", "--unified=0", "--", str(path))
        if staged.returncode != 0:
            continue
        for ahead, line in _late_lines(
            _added_lines(staged.stdout), now, board=path == BOARD
        ):
            problems.append(
                f"(staged) {path}: この行は現在時刻の {ahead:+.0f} 分先を"
                f"名乗っている（許容 {MARGIN_MINUTES} 分）: {line[:80]}"
            )

    return problems, notes


def main() -> int:
    problems, notes = check()
    for note in notes:
        print(f"NOTE: {note}")
    if problems:
        print("REFUSED: ログ行が自分の時刻について嘘をついている")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("ログ行の時刻は commit と整合（追加行のみを見ている）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
