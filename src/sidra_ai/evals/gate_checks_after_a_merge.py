"""Does the timestamp gate still judge when a merge is in the range?

C-1943. ``check_log_times.py`` read git with strict decoding. A combined
diff - what ``git show`` prints for a merge - puts the enclosing line in the
``@@@ ... @@@`` hunk header and truncates it *by bytes*, so a Japanese log
line is cut mid-character and the trailing 0xef arrives with no
continuation. The script raised, printed a traceback, and checked nothing;
to ``check_before_push.sh`` that was simply red, so every push that followed
a concurrent merge was refused for a reason nobody could see.

Reproduced here before writing anything, on the merge the filing names:
strict decoding raises ``'utf-8' codec can't decode byte 0xef``, and the
``errors="replace"`` path returns ~3000 characters. **The byte offset and
character count differ between runs** - the filing measured position 181 and
3002 characters, this reproduction 178 and 2999 - which is the concrete
reason nothing here asserts on either number.

The fix (``errors="replace"``) was already on main. This is the lock, and
locks are only worth having if they fail when the thing they guard is
undone, so each case is run against a real repository with a real merge and
a real Japanese log line. A fixture in ASCII would pass with the bug fully
restored, which is the one way this could have been written to prove
nothing.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .scratch import scratch_dir

_SCRIPT = "check_log_times.py"

#: The fixture line appended by each lane. Japanese, because the defect is a
#: multi-byte character cut by a byte-truncating hunk header (禁じ手 3).
_JA = "ループA 日本語の行（多バイト文字を含む・これがバイト境界で切られる）"

#: The line that has to sit above the change for the defect to appear at all,
#: and the part that took three tries to get right.
#:
#: git names a hunk after the nearest preceding line its funcname heuristic
#: matches, then truncates that name to about forty BYTES. The first fixture
#: had no such line and the header carried no name; the second put the
#: Japanese at the top but let an ASCII filler line sit nearer the change, so
#: git named the filler. Both scored 4/4 with the decode bug fully restored.
#:
#: Read off the real failing merge (`22eebaae`), whose header was
#: ``@@@ ... @@@ unmeasurable→1 のみ・他は不変…``: the named line starts with
#: an ASCII word - which is what makes git pick it - and runs on into
#: Japanese, so the forty-byte cut lands mid-character. The filler between it
#: and the change must start with a digit, like every real log line, so git
#: scans past it.
_ENCLOSING = "unmeasurable→1 " + "のみ・他は不変" * 3
_FILLER = [f"2026-09-17 0{n}:00 UTC filler" for n in range(1, 10)]


@dataclass(frozen=True)
class MergeGateResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, errors="replace")


def _stamp(minutes: int = 0) -> str:
    when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    return when.strftime("%Y-%m-%d %H:%M UTC")


def _repo(root: Path, script_text: str | None = None) -> Path:
    base = Path(scratch_dir(prefix="merge-gate-"))
    origin, work = base / "origin.git", base / "work"
    _run(["git", "init", "--bare", "-b", "main", str(origin)], base)
    _run(["git", "init", "-b", "main", str(work)], base)
    work.mkdir(exist_ok=True)
    for key, value in (("user.email", "loop@example.invalid"), ("user.name", "loop")):
        _run(["git", "config", key, value], work)
    (work / "scripts").mkdir(parents=True, exist_ok=True)
    (work / "scripts" / _SCRIPT).write_text(
        script_text
        if script_text is not None
        else (root / "scripts" / _SCRIPT).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (work / "docs").mkdir(parents=True, exist_ok=True)
    (work / "docs" / "LOOP_LOG.md").write_text(
        "\n".join([_ENCLOSING, *_FILLER]) + "\n", encoding="utf-8"
    )
    (work / "docs" / "BACKLOG.md").write_text("# board\n", encoding="utf-8")
    _run(["git", "add", "-A"], work)
    _run(["git", "commit", "-qm", "base"], work)
    _run(["git", "remote", "add", "origin", str(origin)], work)
    _run(["git", "push", "-q", "origin", "main"], work)
    return work


def _append(work: Path, line: str, message: str) -> None:
    log = work / "docs" / "LOOP_LOG.md"
    log.write_text(log.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
    _run(["git", "add", "-A"], work)
    _run(["git", "commit", "-qm", message], work)


def _make_a_merge(work: Path, mine: str, theirs: str) -> None:
    """Two lanes append Japanese log lines, then one merges the other.

    The merge is what produces the combined diff whose hunk header carries a
    byte-truncated copy of the enclosing Japanese line.
    """

    _run(["git", "checkout", "-q", "-b", "other", "origin/main"], work)
    _append(work, theirs, "other lane")
    _run(["git", "checkout", "-q", "main"], work)
    _append(work, mine, "my lane")

    # Both lanes appended to the end of the same file, so this conflicts -
    # and a conflicted merge is not a merge. The first version of this
    # helper stopped here, leaving `UU docs/LOOP_LOG.md` and no merge commit
    # at all, and every case then ran against an ordinary one-parent commit.
    # It scored 4/4 with the decode bug fully restored. Resolve and commit,
    # keeping BOTH Japanese lines so the combined diff's `@@@` header carries
    # a byte-truncated multi-byte line - which is the whole defect.
    _run(["git", "merge", "--no-edit", "other"], work)
    log = work / "docs" / "LOOP_LOG.md"
    log.write_text(
        "\n".join([_ENCLOSING, *_FILLER, theirs, mine]) + "\n", encoding="utf-8"
    )
    _run(["git", "add", "-A"], work)
    _run(["git", "commit", "-qm", "merge both lanes"], work)

    # And say so if that did not produce a merge, rather than testing
    # nothing quietly a second time.
    merges = _run(["git", "log", "--merges", "--format=%h"], work).stdout.split()
    if not merges:
        raise AssertionError("fixture built no merge commit - the case would prove nothing")
    parents = _run(["git", "log", "-1", "--format=%p"], work).stdout.split()
    if len(parents) < 2:
        raise AssertionError(f"HEAD is not a merge (parents={parents})")

    # And the combined diff must actually be undecodable under strict rules,
    # or the cases below are testing a merge that never had the defect. This
    # is the guard the first two fixtures lacked.
    raw = subprocess.run(
        ["git", "show", "--format=", "--unified=0", "HEAD", "--", "docs/LOOP_LOG.md"],
        cwd=work, capture_output=True,
    ).stdout
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return
    raise AssertionError(
        "fixture's combined diff decodes cleanly - the byte truncation never "
        "happened, so a lock built on it would pass with the bug restored"
    )


def _gate(work: Path) -> subprocess.CompletedProcess:
    return _run(["python3", "scripts/" + _SCRIPT], work)


def evaluate_gate_checks_after_a_merge() -> MergeGateResult:
    root = _root()
    failures: list[str] = []
    passed = 0

    # (A) With a merge in the range carrying Japanese log lines, the gate
    # returns a verdict instead of a traceback.
    work = _repo(root)
    _make_a_merge(work, f"{_stamp()} {_JA} A", f"{_stamp()} {_JA} B")
    done = _gate(work)
    if done.returncode == 0 and "Traceback" not in done.stderr:
        passed += 1
    else:
        failures.append(
            f"(A) merge を含む範囲で門が判定を返さない: rc={done.returncode}"
            f" {done.stderr.strip()[-90:]}"
        )

    # (B) And it is still *checking*: a line 19 minutes in its own future,
    # in the same merge situation, is still refused. Without this, (A) is
    # satisfied by a gate that decodes fine and judges nothing.
    work = _repo(root)
    _make_a_merge(work, f"{_stamp(19)} {_JA} 未来", f"{_stamp()} {_JA} B")
    caught = _gate(work)
    if caught.returncode == 1 and "REFUSED" in caught.stdout:
        passed += 1
    else:
        failures.append(
            "(B) merge を挟むと先の時刻の行を見逃す（置換が検査を盲にした）: "
            f"rc={caught.returncode}"
        )

    # (C) The everyday path - no merge - is unchanged.
    work = _repo(root)
    _append(work, f"{_stamp()} {_JA} 通常", "no merge here")
    plain = _gate(work)
    if plain.returncode == 0:
        passed += 1
    else:
        failures.append(f"(C) merge を挟まない経路の挙動が変わった: rc={plain.returncode}")

    # (D) And when the gate itself breaks, it says so instead of wearing the
    # same face as a refusal. Driven by breaking it for real: `check()` is
    # replaced with one that raises, and the exit code and words are read.
    work = _repo(root)
    broken = (root / "scripts" / _SCRIPT).read_text(encoding="utf-8").replace(
        "def check() -> tuple[list[str], list[str]]:",
        "def check() -> tuple[list[str], list[str]]:\n"
        '    raise UnicodeDecodeError("utf-8", b"\\xef", 0, 1, "invalid continuation byte")',
        1,
    )
    work = _repo(root, script_text=broken)
    _append(work, f"{_stamp()} {_JA} 故障", "a line")
    died = _gate(work)
    if (
        died.returncode == 2
        and "COULD NOT CHECK" in died.stdout
        and "REFUSED" not in died.stdout
    ):
        passed += 1
    else:
        failures.append(
            "(D) 門が自分で落ちたときに拒否と区別できない: "
            f"rc={died.returncode} {died.stdout.strip()[:90]}"
        )

    return MergeGateResult(
        passed=not failures,
        checks_passed=passed,
        checks_total=4,
        failures=tuple(failures),
    )
