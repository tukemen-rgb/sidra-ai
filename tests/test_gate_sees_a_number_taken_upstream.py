"""A number this push claims must not already head somebody else's item (C-1800).

Each loop reads its own copy of the board, takes ``max + 1``, and starts
working. A claim another loop has not pushed yet is not in that copy, so two
loops take the same number. Measured 2026-09-14 across the log and the board:
49 distinct numbers appear in a renumbering record, 9 of them in the last ~28
hours - a count of *records*, so read it as "at least".

Most of that is already caught, and measuring that first changed what this is.
``check_backlog_board.py`` refuses a board where one number heads two items,
which is exactly what a rebase produces when both claims land: the colliding
push is refused today, in a throwaway repository, without anything new.

**One path escaped, and it is the worst one.** Resolve the rebase by keeping
only your own line and the duplicate is gone - nothing refuses, the push lands,
and the other loop's claim is deleted from ``origin/main``. Measured: rc=0, and
their item no longer existed upstream. 厳守事項 5 broken by accident, silently.

So the check below asks whether a number heads a *different* item here and
upstream, with the upstream item's title gone from this board. And the test
that matters is not "was the push refused" but **"is their claim still there
afterwards"**.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_numbers_upstream.py"
THEIRS = "- [~] 確保 **C-0002: 他ループの項目。**\n"
MINE = "- [ ] **C-0002: 私の項目。**\n"


def _env(home: Path) -> dict:
    return {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""), "HOME": str(home),
    }


def _two_loops(home: Path, mine: str, drop_theirs: bool, reachable: bool = True):
    """Two loops taking one number. Returns (rc, output, their claim survived)."""

    root, bare = home / "work", home / "origin.git"
    env = _env(home)
    (root / "scripts").mkdir(parents=True)
    (root / "docs").mkdir()
    for name in ("check_numbers_upstream.py", "check_backlog_board.py"):
        shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)

    def git(*args: str, where: Path | None = None, check: bool = True):
        return subprocess.run(["git", *args], cwd=where or root, env=env,
                              check=check, capture_output=True, text=True,
                              timeout=180)

    subprocess.run(["git", "init", "-q", "--bare", str(bare)], env=env,
                   check=True, capture_output=True, timeout=180)
    base = "# board\n\n- [ ] **C-0001: base.**\n"
    (root / "docs" / "BACKLOG.md").write_text(base, encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("remote", "add", "origin", str(bare))
    git("add", "-A"); git("commit", "-q", "-m", "base"); git("push", "-q", "origin", "main")

    other = home / "other"
    git("clone", "-q", "-b", "main", str(bare), str(other), where=home)
    with (other / "docs" / "BACKLOG.md").open("a", encoding="utf-8") as fh:
        fh.write(THEIRS)
    git("add", "-A", where=other); git("commit", "-q", "-m", "other", where=other)
    git("push", "-q", "origin", "main", where=other)

    with (root / "docs" / "BACKLOG.md").open("a", encoding="utf-8") as fh:
        fh.write(mine)
    git("add", "-A"); git("commit", "-q", "-m", "mine")
    git("fetch", "-q", "origin", "main")
    if git("rebase", "-q", "origin/main", check=False).returncode != 0:
        kept = base + (mine if drop_theirs else THEIRS + mine)
        (root / "docs" / "BACKLOG.md").write_text(kept, encoding="utf-8")
        git("add", "-A")
        subprocess.run(["git", "rebase", "--continue"], cwd=root,
                       env=dict(env, GIT_EDITOR="true"), capture_output=True,
                       text=True, timeout=180)
    if not reachable:
        git("remote", "set-url", "origin", str(home / "gone.git"))

    checked = subprocess.run([sys.executable, "scripts/check_numbers_upstream.py"],
                             cwd=root, env=env, capture_output=True, text=True,
                             timeout=180)
    if checked.returncode == 0 and reachable:
        git("push", "-q", "origin", "main", check=False)
    survived = "他ループの項目" in git(
        "show", "origin/main:docs/BACKLOG.md", check=False).stdout
    return checked.returncode, checked.stdout, survived


def test_the_other_loops_claim_is_not_deleted(tmp_path: Path) -> None:
    """The measurement that matters: their work is still there."""

    rc, said, survived = _two_loops(tmp_path, MINE, drop_theirs=True)

    assert rc != 0, "a push that erases another loop's claim has to be stopped"
    assert survived, "their item was deleted from origin/main"
    assert "REFUSED" in said and "C-0002" in said


def test_it_says_what_to_do_and_does_not_renumber(tmp_path: Path) -> None:
    """禁じ手 ①: a machine rewriting another loop's line is the thing this is
    protecting against, so it refuses and leaves the choice to a person."""

    _, said, _ = _two_loops(tmp_path, MINE, drop_theirs=True)

    assert "Take a fresh number" in said
    assert "Do not" in said and "renumber somebody else" in said


def test_an_ordinary_push_is_not_refused(tmp_path: Path) -> None:
    """禁じ手 ②, and C-1781's standing reminder of what a false refusal costs:
    a number that merely appears in prose is not a claim."""

    mine = "- [ ] **C-0003: 私の項目。**\n      C-0002 は本文で触れるだけ。\n"

    rc, said, survived = _two_loops(tmp_path, mine, drop_theirs=False)

    assert rc == 0, said
    assert survived


def test_an_unreadable_origin_does_not_stop_the_push(tmp_path: Path) -> None:
    """`check_log_times.py`'s precedent: a network blip must not stop every
    loop. The rule it must not break is C-1723's - never print OK for
    something that was not read."""

    rc, said, _ = _two_loops(tmp_path, MINE, drop_theirs=True, reachable=False)

    assert rc == 0
    assert "NOTE" in said and "could not be read" in said
    assert "none collides" not in said, "it must not claim a clean bill of health"


def test_a_board_that_cannot_be_read_does_not_pass(tmp_path: Path) -> None:
    """C-1723 again: a check that reads nothing must not be a green light."""

    empty = tmp_path / "empty"
    (empty / "docs").mkdir(parents=True)
    (empty / "scripts").mkdir()
    for name in ("check_numbers_upstream.py", "check_backlog_board.py"):
        shutil.copy2(ROOT / "scripts" / name, empty / "scripts" / name)
    (empty / "docs" / "BACKLOG.md").write_text("# no items here\n", encoding="utf-8")

    done = subprocess.run([sys.executable, "scripts/check_numbers_upstream.py"],
                          cwd=empty, capture_output=True, text=True, timeout=180)

    assert done.returncode == 2
    assert "read nothing" in done.stdout or "no number was read" in done.stdout


def test_the_rule_is_read_from_headings_not_prose() -> None:
    """One definition of "a number heads an item", shared with the board
    check - so the two cannot drift into different rules."""

    text = CHECK.read_text(encoding="utf-8")

    assert "from check_backlog_board import HEADS, read_items" in text
    assert "read_items(" in text


def test_the_gate_runs_it() -> None:
    gate = (ROOT / "scripts" / "check_before_push.sh").read_text(encoding="utf-8")

    assert "check_numbers_upstream.py" in gate
    assert 'if [ "$?" -ne 0 ]; then' in gate, "the exit status has to be read"
