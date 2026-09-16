"""Does the board's gate let a completion claim a number nobody can find?

C-1893. The item asked for a check that the names on the board resolve, and
its two load-bearing assumptions were both measured before this was written,
because both were wrong:

* It said six `[x] 完了` records name a metric the repository no longer has,
  so they cannot be re-measured. They do not. All five 09-05/09-06 attract
  records name ``creation_attract_demo`` - the metric the five were merged
  into - and the sixth names ``creation_draw_request_makes_art``. Both exist.
  **No completion on this board is unfalsifiable.** What is stale is the
  *brief*, the 「→ 動かす数字:」 line written at filing time, which is a plan
  rather than a claim.
* It said ``check_backlog_board.MOVES`` could do the extraction. Over the
  last forty commits that ticked a box, **MOVES matches zero added lines on
  a completion push**: the brief is not re-added when the box is ticked. A
  check built on it could never fire on the case the item exists for.

So what is guarded here is the property that *is* true and is enforced by
nothing: the receipt on a completion line names a metric that exists. It
holds in 57 of the last 57 completions, and the day it stops holding is the
day a number stops being re-measurable.

Three cases, and each is run against a real git repository with a real
``origin``, by really invoking the check as a child process and reading its
exit code - not by importing a function and trusting it.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .scratch import scratch_dir

#: The two scripts the check needs beside it: itself, and the board reader
#: it borrows ``MOVES`` from rather than keeping a second copy.
_SCRIPTS = ("check_metric_names.py", "check_backlog_board.py")

#: A board that is already carrying a stale plan line - the state every real
#: run starts from. Case B exists to prove this never blocks anybody.
_BASE_BOARD = """# 板

## C-0l 積み上げ

- [ ] **C-0001: 既に在る計画行が、統合で置き換わった指標を名指している。**
      → 動かす数字: `vanished_plan_name` （統合済み・行き先未記載）
- [x] 完了 2026-01-01 00:00 UTC ループZ（`living_metric_name` **1→2**） **C-0002: 済んだもの。**
"""


@dataclass(frozen=True)
class MetricNamesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def _stand_in(root: Path) -> Path:
    """A repository shaped like this one: scripts, a board, and an origin.

    The check reads ``origin/main..HEAD``, so a stand-in without a real
    remote would exercise the "cannot read upstream" path instead of the
    one under test - which is how a probe ends up passing for a reason that
    has nothing to do with the rule.
    """

    base = Path(scratch_dir(prefix="metric-names-"))
    origin, work = base / "origin.git", base / "work"
    _run(["git", "init", "--bare", "-b", "main", str(origin)], base)
    _run(["git", "init", "-b", "main", str(work)], base)
    work.mkdir(exist_ok=True)
    _run(["git", "config", "user.email", "loop@example.invalid"], work)
    _run(["git", "config", "user.name", "loop"], work)
    (work / "scripts").mkdir(parents=True, exist_ok=True)
    for name in _SCRIPTS:
        (work / "scripts" / name).write_text(
            (root / "scripts" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (work / "docs").mkdir(parents=True, exist_ok=True)
    (work / "docs" / "BACKLOG.md").write_text(_BASE_BOARD, encoding="utf-8")
    # The name the completions in the base board claim has to live
    # somewhere, or the base state is already red for an unrelated reason.
    (work / "scripts" / "product_metrics.py").write_text(
        'c.add("living_metric_name", "生きている数字", 2.0)\n', encoding="utf-8"
    )
    _run(["git", "add", "-A"], work)
    _run(["git", "commit", "-qm", "base"], work)
    _run(["git", "remote", "add", "origin", str(origin)], work)
    _run(["git", "push", "-q", "origin", "main"], work)
    return work


def _check(work: Path) -> subprocess.CompletedProcess:
    """The check as the gate runs it, plus ``--list``.

    The stale-plan names sit behind ``--list`` so the pre-push gate stays
    readable; case B reads them by name, so it asks for them. The control
    run is what caught this - the flag was added to the script first and
    the judge scored 2/3 until it was added here too.
    """

    return _run(["python3", "scripts/check_metric_names.py", "--list"], work)


def _push_board(work: Path, added: str, message: str) -> None:
    board = work / "docs" / "BACKLOG.md"
    board.write_text(board.read_text(encoding="utf-8") + added, encoding="utf-8")
    _run(["git", "add", "-A"], work)
    _run(["git", "commit", "-qm", message], work)


def evaluate_board_metric_names_resolve() -> MetricNamesResult:
    root = _root()
    failures: list[str] = []
    passed = 0

    # (A) A completion this push adds, naming a number that is nowhere in
    # the repository, is refused - and the refusal says which name.
    work = _stand_in(root)
    _push_board(
        work,
        "- [x] 完了 2026-01-02 00:00 UTC ループZ"
        "（`gone_without_a_trace` **2→3**） **C-0003: 消えた名前で完了を名乗る。**\n",
        "claim a vanished metric",
    )
    done = _check(work)
    if done.returncode == 1 and "gone_without_a_trace" in done.stdout:
        passed += 1
    else:
        failures.append(
            f"(A) 消えた指標名の完了が拒否されなかった: rc={done.returncode}"
        )

    # (B) And the lines that are already there - plus a *new* filing naming a
    # metric that does not exist yet, which is how every new number is
    # proposed - do not stop the push. Both items filed on 2026-09-16 were
    # of this shape; refusing them would have refused the push that claimed
    # this item.
    work = _stand_in(root)
    _push_board(
        work,
        "- [ ] **C-0004: これから作る数字を起票する。**\n"
        "      → 動かす数字: `not_built_yet_metric` **unmeasurable→3**（新設）\n"
        "- [記録] 未修正・計測のみ 2026-01-02 ループZ"
        "（`measured_never_built` は実装しないと決めた） **C-0005: 測っただけ。**\n",
        "file a new metric and a record",
    )
    filed = _check(work)
    reported = "vanished_plan_name" in filed.stdout and "not_built_yet_metric" in filed.stdout
    if filed.returncode == 0 and reported:
        passed += 1
    else:
        failures.append(
            "(B) 既存の計画行・新設の起票・[記録] が push を止めた、"
            f"または報告されなかった: rc={filed.returncode} 報告={reported}"
        )

    # (C) A name that lives in some *other* judge, not in
    # ``product_metrics.py``, resolves. The filer got this wrong first and
    # counted 13 missing names; five of them were in other judges. The judge
    # is not one script.
    work = _stand_in(root)
    (work / "scripts" / "check_other_judge.py").write_text(
        "# the only place this number is defined\nOTHER = 'answerable_direct_stand_in'\n",
        encoding="utf-8",
    )
    _push_board(
        work,
        "- [x] 完了 2026-01-02 00:00 UTC ループZ"
        "（`answerable_direct_stand_in` **4→5**） **C-0006: 別の判定器の数字。**\n",
        "claim a metric that lives in another judge",
    )
    other = _check(work)
    if other.returncode == 0:
        passed += 1
    else:
        failures.append(
            "(C) 別の判定器にしか無い指標名が拒否された"
            f"（`product_metrics.py` だけを見ている）: rc={other.returncode}"
        )

    return MetricNamesResult(
        passed=not failures,
        checks_passed=passed,
        checks_total=3,
        failures=tuple(failures),
    )
