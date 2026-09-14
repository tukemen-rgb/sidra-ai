"""C-1826: the board-times probe must not depend on what minute it started.

``board_times_match_the_commit`` (C-1813) builds a throwaway repository, writes
a board line, and runs ``check_log_times.py`` against it. Its hidden-minute case
wrote the minute as a hardcoded 「4x」 whatever the real minute was, and the check
reads 「4x」 as :40 - the earliest minute that spelling can mean. So the line meant
to sit *at* its own commit claimed up to +40 minutes, and the 30-minute margin
refused it for every run starting in the first ten minutes of an hour.

Not a flake: this loop's routine fires at :05, inside that window. Measured at
18:06 on 2026-09-14, the honest hidden-minute line was REFUSED while the same
line carrying its real minute passed.

The clock is pinned rather than waited for, and both directions are checked at
each minute - a probe that stopped refusing the future line would "pass" too.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_log_times.py"

#: Inside the old broken window, at its edges, and well outside it.
_MINUTES = (0, 5, 9, 10, 35, 50)


def _hidden_minute_stamp(when: dt.datetime) -> str:
    """The spelling the fixed probe writes: the board's 「Nx」 form, real tens."""

    return when.strftime("%Y-%m-%d %H:") + f"{when.minute // 10}x UTC"


def _verdict(tmp_path: Path, minute: int, ahead: int) -> int:
    root, bare = tmp_path / "work", tmp_path / "origin.git"
    base = dt.datetime.now(dt.timezone.utc).replace(
        minute=minute, second=0, microsecond=0
    )
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_AUTHOR_DATE": base.isoformat(), "GIT_COMMITTER_DATE": base.isoformat(),
        "PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path),
    }
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], env=env, check=True)
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "LOOP_LOG.md").write_text("# log\n", encoding="utf-8")
    (root / "docs" / "BACKLOG.md").write_text("# board\n\n", encoding="utf-8")
    for command in (
        ["init", "-q", "-b", "main"], ["remote", "add", "origin", str(bare)],
        ["add", "-A"], ["commit", "-q", "-m", "base"], ["push", "-q", "origin", "main"],
    ):
        subprocess.run(["git", *command], cwd=root, env=env, check=True,
                       capture_output=True)
    stamp = _hidden_minute_stamp(base + dt.timedelta(minutes=ahead))
    with (root / "docs" / "BACKLOG.md").open("a", encoding="utf-8") as handle:
        handle.write(f"- [~] 作業中 {stamp} ループA **C-0999: 試験の項目。**\n")
    for command in (["add", "-A"], ["commit", "-q", "-m", "claim"]):
        subprocess.run(["git", *command], cwd=root, env=env, check=True,
                       capture_output=True)
    return subprocess.run(
        ["python3", str(_SCRIPT)], cwd=root, env=env,
        capture_output=True, text=True, timeout=120,
    ).returncode


@pytest.mark.parametrize("minute", _MINUTES)
def test_an_honest_line_passes_at_any_minute(tmp_path, minute: int) -> None:
    # The old spelling refused this at :00, :05 and :09.
    assert _verdict(tmp_path, minute, ahead=0) == 0


@pytest.mark.parametrize("minute", _MINUTES)
def test_a_future_line_is_still_refused_at_any_minute(tmp_path, minute: int) -> None:
    # The other direction: a probe that stopped refusing would also stop
    # failing the first test, and "always passes" is not a gate.
    assert _verdict(tmp_path, minute, ahead=279) == 1


def test_the_spelling_is_still_the_boards_own_form() -> None:
    # 「13:4x」 is how the board writes it; only the tens digit must be real.
    when = dt.datetime(2026, 9, 14, 18, 6, tzinfo=dt.timezone.utc)
    assert _hidden_minute_stamp(when) == "2026-09-14 18:0x UTC"
    assert _hidden_minute_stamp(when.replace(minute=47)) == "2026-09-14 18:4x UTC"
