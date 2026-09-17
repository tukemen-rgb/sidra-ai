"""C-1733: a log line must not claim a time it has not reached.

`docs/LOOP_LOG.md` is read as a history and the stamp at the head of each
line is what orders it. Measured 2026-09-12 over the whole file - 1818
timestamped lines, a census and not a sample: 95.3% sit within +5 minutes of
the commit that added them (median -0.6, p90 +1.6), but the tail runs to
p98 +37.7, p99 +175.6 and a worst case of +702.6 minutes. 86 lines lead by
more than five minutes, 68 of them from one loop whose lead grew through the
day. Reading order steps backwards at 129 of 1817 adjacent pairs, so on
2026-09-12 the log carried lines dated 09-13 above lines dated 09-12.

Two things keep this from blocking everybody:

* it judges only the lines a push *adds*, so the 86 already in the file are
  left alone - reading the whole file is the trap C-1728 walked into; and
* the margin is 30 minutes, against a measured honest lag whose worst cases
  are ループA +20.2, ループB +18.5, 進捗監視 +17.6. (The item proposing this
  put the honest maximum at +17.6; the census says +20.2, and the margin was
  chosen against the census.)
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_log_times.py"

_spec = importlib.util.spec_from_file_location("check_log_times", SCRIPT)
log_times = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(log_times)


def _repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, dict]:
    """A repository with an origin, because the check asks what is pushed."""

    work, bare = tmp_path / "work", tmp_path / "origin.git"
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path),
    }
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], env=env, check=True)
    (work / "docs").mkdir(parents=True)
    (work / "docs" / "LOOP_LOG.md").write_text("# log\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, env=env, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=work, env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=work, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=work, env=env, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=work, env=env, check=True)
    return work, env


def _commit_line(work: pathlib.Path, env: dict, minutes_ahead: int) -> None:
    stamp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes_ahead)).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    with (work / "docs" / "LOOP_LOG.md").open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} ループA 行\n")
    subprocess.run(["git", "add", "-A"], cwd=work, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add a line"], cwd=work, env=env, check=True)


def _run(work: pathlib.Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python", str(SCRIPT)], cwd=work, env=env,
        capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize("ahead", [2, 19, 31, 120, 700])
def test_a_line_claiming_a_time_it_has_not_reached_is_refused(
    ahead: int, tmp_path: pathlib.Path
) -> None:
    work, env = _repo(tmp_path)
    _commit_line(work, env, ahead)

    done = _run(work, env)

    assert done.returncode == 1, done.stdout
    assert "REFUSED" in done.stdout
    assert "分先" in done.stdout


@pytest.mark.parametrize("ahead", [-60, -5, 0])
def test_an_honestly_written_line_still_passes(ahead: int, tmp_path: pathlib.Path) -> None:
    """The other direction. A check that refused every lead would score full
    marks on the first half alone.

    C-1914 removed +18, +21 and +29 from this list. They were here as "the
    measured honest lag", and they are not honest: a loop that writes its
    line at the head of a cycle and commits after the work produces a
    *negative* lead, which is what -60 and -5 are. `date -u` floors, so a
    stamp is never later than the moment of writing and the commit is later
    still - an honestly written line cannot lead at all. Measured over 444
    added lines in the last 400 commits, 369 lead by nothing; every
    positive lead is a typed time rather than a read one.
    """

    work, env = _repo(tmp_path)
    _commit_line(work, env, ahead)

    done = _run(work, env)

    assert done.returncode == 0, done.stdout


def test_only_the_added_lines_are_judged(tmp_path: pathlib.Path) -> None:
    """The trap C-1728 walked into. A future-dated line already in the
    history must not refuse a later, honest push."""

    work, env = _repo(tmp_path)
    _commit_line(work, env, 700)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=work, env=env, check=True)
    # Now a second, honest line on top of that history.
    _commit_line(work, env, 0)

    done = _run(work, env)

    assert done.returncode == 0, f"an old line refused a new push: {done.stdout}"


def test_the_real_log_is_not_read_as_a_whole(tmp_path: pathlib.Path) -> None:
    """Stated as the contrast it is: a whole-file reading would refuse on a
    line that leads its commit, and the check is green on this repository
    anyway, because it judges only the lines a commit added.

    The leading line is written here rather than looked for in the real
    log. It used to be looked for, with the premise asserted first - and
    the premise is the weather: whether some other loop happens to have a
    future-dated line in the log at the moment the suite runs. It held for
    days and then did not, and the failure said nothing about this code
    (C-1746 hit it). What the test is about is the contrast, and the
    contrast can be built.
    """

    now = dt.datetime.now(dt.timezone.utc)
    ahead = now + dt.timedelta(minutes=log_times.MARGIN_MINUTES + 10)
    whole = (REPO / "docs" / "LOOP_LOG.md").read_text(encoding="utf-8").split("\n")
    whole.append(ahead.strftime("%Y-%m-%d %H:%M UTC ループA started"))

    assert log_times._late_lines(whole, now), (
        "read as a whole, a line stamped past the margin is refused"
    )
    assert log_times.check()[0] == [], (
        "the real log is green, because only the lines a commit added are judged"
    )


def test_the_margin_does_not_come_from_the_lines_it_judges() -> None:
    """C-1914. This used to assert ``MARGIN_MINUTES > 20.2`` because "the
    worst honest lag measured across every loop is ループA's +20.2" - but
    that +20.2 was a leading line, which is the thing the check exists to
    refuse. The margin was measured off the violation and then used to
    decide how much of it to allow.

    What replaces it is the mechanism. A stamp comes from `date -u`, which
    floors to the minute, and the commit time comes from git; writing
    happens before committing, so an honest line's lead is never positive.
    The margin is therefore a small concession for a stamp rounded up by a
    minute, not a percentile of the leading lines.
    """

    assert log_times.MARGIN_MINUTES <= 1, (
        "anything wider re-admits the leads this check exists to refuse"
    )
    assert log_times.MARGIN_MINUTES >= 0, "a negative margin refuses honest lines"
