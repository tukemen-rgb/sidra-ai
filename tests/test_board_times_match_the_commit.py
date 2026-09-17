"""The board's lines must not claim times they have not reached (C-1813).

C-1733 taught ``check_log_times.py`` that a log line must not lead its own
commit, and pointed it at ``docs/LOOP_LOG.md`` alone. The board stamps times in
the same shape, and nothing read them.

Census 2026-09-14 with ``git blame --line-porcelain`` over every timestamped
board line - 687 lines, not a sample: **73 (10.6%) lead their own commit by
more than 30 minutes**, median +83, worst +719 (about 12 hours), spread over
ten days. One live that morning claimed ``13:4x`` on a line committed at 09:01.

The cost is the one C-1733 already recorded: the stall watch reads the time on
a ``[~]`` line to decide whether an item has been sitting, so a claim hours
ahead looks like work that has not started and a stalled item never rings.

Narrow on purpose, and the narrowness is the part worth testing: **only the
lines a push adds**. Judging the 73 already there would make every loop red on
the first run - C-1728's trap, which this must not re-enter. Those lines are
not touched; fixing them would be a separate decision.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_log_times.py"


def _repo(home: Path, minutes_ahead: int, hide_minute: bool = False,
          old_lines: int = 0, into_log: bool = False) -> tuple[int, str]:
    """A line stamped `minutes_ahead` from now, committed, then checked."""

    root, bare = home / "work", home / "origin.git"
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""), "HOME": str(home),
    }
    (root / "scripts").mkdir(parents=True)
    (root / "docs").mkdir()
    shutil.copy2(CHECK, root / "scripts" / CHECK.name)

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, env=env, check=True,
                       capture_output=True, timeout=180)

    subprocess.run(["git", "init", "-q", "--bare", str(bare)], env=env, check=True,
                   capture_output=True, timeout=180)
    (root / "docs" / "LOOP_LOG.md").write_text("# log\n", encoding="utf-8")
    # History as the loops already have it: lines that lead their commit by
    # hours, committed BEFORE the push under test so they are not "added".
    stale = "# board\n\n"
    for n in range(old_lines):
        far = (dt.datetime.now(dt.timezone.utc)
               + dt.timedelta(minutes=600 + n)).strftime("%Y-%m-%d %H:%M UTC")
        stale += f"- [x] 完了 {far} ループB **C-{900 + n}: 古い行。**\n"
    (root / "docs" / "BACKLOG.md").write_text(stale, encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("remote", "add", "origin", str(bare))
    git("add", "-A"); git("commit", "-q", "-m", "base"); git("push", "-q", "origin", "main")

    when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes_ahead)
    # A hidden minute keeps its tens digit: `10:4x` means 10:40-10:49, and the
    # checker reads it as the earliest it can mean. The stamp therefore has to
    # hide the minute the line actually has, not a fixed "4x" - written as a
    # constant, this test failed for the first ten minutes of every hour,
    # because "HH:4x" read as HH:40 is then 31-40 minutes ahead of a commit
    # made at HH:00-HH:09 (measured 2026-09-15 10:06 UTC: "+34 分先").
    stamp = (
        f"{when:%Y-%m-%d %H}:{when.minute // 10}x UTC"
        if hide_minute
        else when.strftime("%Y-%m-%d %H:%M UTC")
    )
    if into_log:
        with (root / "docs" / "LOOP_LOG.md").open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} ループA started\n")
    else:
        with (root / "docs" / "BACKLOG.md").open("a", encoding="utf-8") as fh:
            fh.write(f"- [~] 作業中 {stamp} ループA **C-0999: 試験の項目。**\n")
    git("add", "-A"); git("commit", "-q", "-m", "claim")

    done = subprocess.run([sys.executable, "scripts/check_log_times.py"], cwd=root,
                          env=env, capture_output=True, text=True, timeout=180)
    return done.returncode, done.stdout


def test_a_board_line_from_the_future_is_refused(tmp_path: Path) -> None:
    rc, said = _repo(tmp_path, minutes_ahead=279)

    assert rc == 1
    assert "REFUSED" in said
    assert "BACKLOG" in said, "the reader has to be told which file"
    lead = int(re.search(r"\+(\d+) 分先", said).group(1))
    assert 270 <= lead <= 280, said


@pytest.mark.parametrize("ahead", [0, -5, -90], ids=["same-minute", "behind", "long-cycle"])
def test_an_honest_board_line_passes(tmp_path: Path, ahead: int) -> None:
    """Without this, a check that refused everything would score full marks.

    C-1914 replaced the +21 case. It was here as "inside the measured
    honest lag (worst case +20.2)", but a +20.2 line is one that claimed a
    time before it existed - the violation, not the baseline. An honest
    board line is written with `date -u` and committed afterwards, so it
    trails its commit: that is what -5 and -90 are, the second standing for
    a claim written at the head of a long cycle.
    """

    rc, said = _repo(tmp_path, minutes_ahead=ahead)

    assert rc == 0, said


def test_the_lines_already_on_the_board_do_not_turn_it_red(tmp_path: Path) -> None:
    """C-1728's trap: judging history blocks every loop on the first run.
    73 is the real count from the 2026-09-14 census."""

    rc, said = _repo(tmp_path, minutes_ahead=0, old_lines=73)

    assert rc == 0, said


def test_the_hidden_minute_spelling_is_judged(tmp_path: Path) -> None:
    """`13:4x` is the commonest spelling on the board. Skipping it would mean
    skipping most of what there is to check."""

    rc, said = _repo(tmp_path, minutes_ahead=279, hide_minute=True)

    assert rc == 1
    assert "REFUSED" in said


def test_the_hidden_minute_is_read_as_the_earliest_it_can_mean(tmp_path: Path) -> None:
    """`x` -> 0, so the lead reported is a lower bound and the rounding never
    favours the check. An honest line written as `HH:4x` must still pass."""

    rc, said = _repo(tmp_path, minutes_ahead=0, hide_minute=True)

    assert rc == 0, said


def test_the_log_file_is_still_judged_exactly_as_before(tmp_path: Path) -> None:
    """C-1733's behaviour is extended, not replaced."""

    assert _repo(tmp_path / "late", minutes_ahead=700, into_log=True)[0] == 1
    assert _repo(tmp_path / "honest", minutes_ahead=0, into_log=True)[0] == 0


def test_only_item_headings_are_read_not_measurement_times() -> None:
    """The board's bodies quote when something was measured - a fact about the
    measurement, not a claim about when the line was written. Reading those
    would refuse honest records of past work."""

    sys.path.insert(0, str(ROOT / "scripts"))
    import check_log_times as clt

    body = "      **実測（2026-09-14 08:2x UTC・この木）**: 何かを測った。"
    heading = "- [~] 作業中 2026-09-14 08:2x UTC ループA **C-0001: 何か。**"

    assert clt._claimed(body, board=True) is None
    assert clt._claimed(heading, board=True) is not None
