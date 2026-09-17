"""Can a line claim a time it has not reached yet, and still be pushed?

C-1914. The gate that judges log and board timestamps allowed a line to
lead its own commit by up to 30 minutes, and the number came from a census
of the leading lines themselves - "the measured honest lag tops out at
+20.2". That +20.2 is not honest lag. A stamp is written by reading the
clock and the commit time is written by git from the same clock, and the
writing happens first, so an honestly written line can only ever be
*behind*. The margin was measured off the violation and then used to
decide how much of it to permit.

Re-measured before changing anything, over the last 400 commits and the
444 added lines the gate reads: 75 lead their commit at all and **42
(9.5%) lead by a full minute or more**, worst +19.3, with none of them
failing under the old margin. The filing's own census said 42 and 9.5%,
and it was right - worth recording, because on this board a filing's
premise usually is not.

The first explanation written for the new margin was wrong and measuring
caught it: it called the 33 sub-minute leads a truncation artefact.
Flooring to the minute can only make a line look *earlier*, never later,
so truncation cannot produce a positive lead at all. Those 33 spread
evenly across 0.03..0.97 - the signature of a stamp written one minute
past its commit's minute, which is the same defect in its mildest form.
The margin of 1 is therefore a stated concession, not a derivation.

By lane those 42 are: ループA 18, 辛口ユーザー 10, 辛口クリエイター 8,
進捗監視 4, 辛口コメンテーター 2. The lane that tightened the gate wrote
the largest share of what it now refuses.

Four cases, each run against a real repository with a real origin, by
invoking the gate as a child process and reading its exit code.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .scratch import scratch_dir

#: What the stand-in needs beside it to be the thing under test.
_SCRIPT = "check_log_times.py"


@dataclass(frozen=True)
class TimesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def _stand_in(root: Path) -> Path:
    """A repository the gate can read: scripts, docs, and an origin.

    The gate judges ``origin/main..HEAD``, so without a real remote it
    takes the "cannot read upstream" path and passes for a reason that has
    nothing to do with timestamps.
    """

    base = Path(scratch_dir(prefix="times-ahead-"))
    origin, work = base / "origin.git", base / "work"
    _run(["git", "init", "--bare", "-b", "main", str(origin)], base)
    _run(["git", "init", "-b", "main", str(work)], base)
    work.mkdir(exist_ok=True)
    _run(["git", "config", "user.email", "loop@example.invalid"], work)
    _run(["git", "config", "user.name", "loop"], work)
    (work / "scripts").mkdir(parents=True, exist_ok=True)
    (work / "scripts" / _SCRIPT).write_text(
        (root / "scripts" / _SCRIPT).read_text(encoding="utf-8"), encoding="utf-8"
    )
    (work / "docs").mkdir(parents=True, exist_ok=True)
    (work / "docs" / "LOOP_LOG.md").write_text("# log\n", encoding="utf-8")
    (work / "docs" / "BACKLOG.md").write_text("# board\n", encoding="utf-8")
    _run(["git", "add", "-A"], work)
    _run(["git", "commit", "-qm", "base"], work)
    _run(["git", "remote", "add", "origin", str(origin)], work)
    _run(["git", "push", "-q", "origin", "main"], work)
    return work


def _commit_line(work: Path, path: str, line: str) -> None:
    target = work / path
    target.write_text(target.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
    _run(["git", "add", "-A"], work)
    _run(["git", "commit", "-qm", "a line"], work)


def _gate(work: Path) -> subprocess.CompletedProcess:
    return _run(["python3", "scripts/check_log_times.py"], work)


def _stamp(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%d %H:%M UTC")


def evaluate_board_times_do_not_run_ahead() -> TimesResult:
    root = _root()
    failures: list[str] = []
    passed = 0

    # (A) A board line claiming 19 minutes in its own future is refused -
    # the live example the item was filed on (`1118f57a` carried a claim
    # line stamped 19 minutes before that commit existed).
    work = _stand_in(root)
    ahead = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=19)
    _commit_line(
        work, "docs/BACKLOG.md", f"- [~] 作業中 {_stamp(ahead)} ループA **C-0001: 未来。**"
    )
    done = _gate(work)
    if done.returncode == 1 and "date -u" in done.stdout:
        passed += 1
    else:
        failures.append(
            f"(A) 19 分先を名乗る板の行が拒否されないか、直し方を言っていない: rc={done.returncode}"
        )

    # (B) And a line stamped in the minute it was committed passes. This is
    # the control: a gate that refuses everything would score (A) for free.
    work = _stand_in(root)
    _commit_line(
        work,
        "docs/LOOP_LOG.md",
        f"{_stamp(dt.datetime.now(dt.timezone.utc))} ループA started",
    )
    honest = _gate(work)
    if honest.returncode == 0:
        passed += 1
    else:
        failures.append(
            f"(B) commit と同じ分の正直な行が落ちた（門が常に赤い）: rc={honest.returncode}"
            f" {honest.stdout.strip()[:120]}"
        )

    # (C) 「13:4x」 hides the minute and is read as the EARLIEST minute it
    # can mean, so the lead this reports is a lower bound. Read the other
    # way the same line would be nine minutes ahead and fail, so this is a
    # real contrast rather than a spelling that happens to pass.
    work = _stand_in(root)
    now = dt.datetime.now(dt.timezone.utc)
    hidden = now.strftime("%Y-%m-%d %H:") + now.strftime("%M")[0] + "x UTC"
    _commit_line(work, "docs/BACKLOG.md", f"- [~] 作業中 {hidden} ループA **C-0002: 伏せ字。**")
    vague = _gate(work)
    if vague.returncode == 0:
        passed += 1
    else:
        failures.append(
            f"(C) 「{hidden}」の下限読みが壊れ、伏せ字が違反に化けた: rc={vague.returncode}"
            f" {vague.stdout.strip()[:120]}"
        )

    # (D) And a history too short to read reports unmeasurable, not zero.
    # A shallow clone answering "0 lines run ahead" is the failure C-1723
    # named: a check that read nothing must not look like health.
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "_times_for_census", root / "scripts" / _SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_times_for_census"] = module
    spec.loader.exec_module(module)
    shallow = _stand_in(root)
    census_here = _run(
        [
            "python3",
            "-c",
            "import sys; sys.path.insert(0, 'scripts');"
            "from check_log_times import census; print(census())",
        ],
        shallow,
    )
    if census_here.stdout.strip() == "None":
        passed += 1
    else:
        failures.append(
            "(D) 浅い履歴で census が unmeasurable を返さなかった"
            f"（0 を健全と読めてしまう）: {census_here.stdout.strip()[:120]}"
        )

    return TimesResult(
        passed=not failures,
        checks_passed=passed,
        checks_total=4,
        failures=tuple(failures),
    )
