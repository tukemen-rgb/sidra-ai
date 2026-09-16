"""The gate is reached by git, not by remembering to reach for it (C-1794).

``scripts/check_before_push.sh`` has existed since C-1660, and its own first
lines say why: three slips in one session, every one of them a check that
printed the problem while the next command ran anyway. On 2026-09-13 23:47 it
happened to the gate itself - ``20225c40`` joined it to ``git push`` with
``;``, the gate printed ``REFUSED: the board reports an inconsistency``, and
the push went through. An inconsistent board landed on main and turned every
loop's gate red.

Nothing about the gate was wrong. It was reached by memory, and five spellings
of that memory were in circulation: ``&&``, ``;``, ``| grep -q``, and
``| tail -1`` - the last one worst, because a pipeline's exit status is the
last command's, so the gate's verdict is discarded outright.

Measured in a throwaway repository with a real remote, before the fix: with a
doubled item number in the board, ``bash gate ; git push`` landed the commit
(rc=0). With ``core.hooksPath`` pointing at a tracked ``.githooks/pre-push``,
the same spelling failed (rc=1).

Both halves are needed and this file checks both. A hook nobody configures
does nothing - **hooks do not travel with a clone** - and a procedure written
with ``;`` teaches the accident it is meant to prevent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-push"
GATE = ROOT / "scripts" / "check_before_push.sh"
BOARD = ROOT / "docs" / "BACKLOG.md"

#: An item number heading two items: the shape that actually landed.
DOUBLED = "- [ ] **C-9999: 実験用の項目（この複製だけに在る）。**\n"


def _section(name: str) -> str:
    """The named section of the board, up to the next heading."""

    lines = BOARD.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith(name):
            rest = lines[i + 1:]
            end = next((j for j, l in enumerate(rest) if l.startswith("## ")), len(rest))
            return "\n".join(rest[:end])
    return ""


def _repo(home: Path, board: str, wire: bool = True) -> tuple[Path, dict]:
    """A repository carrying the hook, the scripts it calls, and a board.

    The gate runs four checks. Three of them have to be *able* to pass, or a
    refusal would say nothing about the board - so the tree gets one clean
    judge for the scratch scan and a log the time check accepts.
    """

    root, bare = home / "work", home / "origin.git"
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""), "HOME": str(home),
    }
    (root / "scripts").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / ".githooks").mkdir()
    (root / "src" / "sidra_ai" / "evals").mkdir(parents=True)
    # Every script the gate calls: one missing makes the gate red for a
    # reason unrelated to the board, which the consistent-board control then
    # catches (it did, when C-1800 added a fourth check).
    for name in ("check_before_push.sh", "check_log_times.py",
                 "check_eval_scratch.py", "check_backlog_board.py",
                 "check_numbers_upstream.py", "check_metric_names.py"):
        shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
    shutil.copy2(HOOK, root / ".githooks" / "pre-push")
    (root / ".githooks" / "pre-push").chmod(0o755)
    (root / "src" / "sidra_ai" / "evals" / "scratch.py").write_text(
        '"""helper"""\n\n\ndef scratch_dir(prefix=""):\n    return "/tmp"\n',
        encoding="utf-8",
    )
    (root / "src" / "sidra_ai" / "evals" / "one.py").write_text(
        "from sidra_ai.evals.scratch import scratch_dir\n\n\n"
        "def go():\n    return scratch_dir()\n", encoding="utf-8",
    )
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (root / "docs" / "BACKLOG.md").write_text(board, encoding="utf-8")
    (root / "docs" / "LOOP_LOG.md").write_text("# log\n", encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, env=env, check=True,
                       capture_output=True, text=True, timeout=180)

    subprocess.run(["git", "init", "-q", "--bare", str(bare)], env=env, check=True,
                   capture_output=True, timeout=180)
    git("init", "-q", "-b", "main")
    git("remote", "add", "origin", str(bare))
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    # The history lands before the hook is wired: a repository that has never
    # pushed is not the situation under test, and with a bad board the gate
    # would refuse this push too, which would prove nothing about the spelling.
    git("push", "-q", "origin", "main")
    if wire:
        git("config", "core.hooksPath", ".githooks")
    return root, env


def _push_with_semicolon(root: Path, env: dict) -> int:
    """The spelling that caused the incident: the gate's verdict discarded."""

    (root / "docs" / "LOOP_LOG.md").open("a", encoding="utf-8").write("\n")
    subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True,
                   capture_output=True, timeout=180)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=root, env=env,
                   check=True, capture_output=True, timeout=180)
    return subprocess.run(
        ["bash", "-c",
         "bash scripts/check_before_push.sh >/dev/null 2>&1 ; git push -q origin main"],
        cwd=root, env=env, capture_output=True, text=True, timeout=300,
    ).returncode


def test_the_hook_is_tracked_and_executable() -> None:
    assert HOOK.exists(), "a hook that is not in the repository is not shared"
    listed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".githooks/pre-push"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert listed.returncode == 0, "the hook has to be tracked, not local"
    assert os.access(HOOK, os.X_OK), "git will not run a hook it cannot execute"


def test_an_inconsistent_board_stops_the_push(tmp_path: Path) -> None:
    """The measurement, done by pushing rather than by reading the hook."""

    board = BOARD.read_text(encoding="utf-8") + "\n" + DOUBLED + DOUBLED
    root, env = _repo(tmp_path, board)

    assert _push_with_semicolon(root, env) != 0, (
        "the gate refused and the ';' threw that away - only the hook can stop this"
    )


def test_a_consistent_board_still_pushes(tmp_path: Path) -> None:
    """The control. Without it, a hook that refused everything would pass the
    test above and stop every loop."""

    root, env = _repo(tmp_path, BOARD.read_text(encoding="utf-8"))

    assert _push_with_semicolon(root, env) == 0


def test_without_the_wiring_the_same_push_lands(tmp_path: Path) -> None:
    """Why the procedure has to carry `core.hooksPath`: this is what a fresh
    clone does, and it is the incident, reproduced."""

    board = BOARD.read_text(encoding="utf-8") + "\n" + DOUBLED + DOUBLED
    root, env = _repo(tmp_path, board, wire=False)

    assert _push_with_semicolon(root, env) == 0, (
        "unwired, the bad board lands - which is what happened on 2026-09-13"
    )


@pytest.mark.parametrize(
    "name", ["SKIP", "SKIP_GATE", "SKIP_HOOKS", "NO_VERIFY", "FORCE", "CI"]
)
def test_no_environment_variable_waves_the_hook_through(
    tmp_path: Path, name: str
) -> None:
    """禁じ手 ①. An escape hatch is the thing everybody learns to set, and it
    would make the hook decorative. `--no-verify` is deliberately left working:
    it cannot be blocked from inside a hook and does not need to be - typing it
    is a decision, and this exists to stop an accident."""

    board = BOARD.read_text(encoding="utf-8") + "\n" + DOUBLED + DOUBLED
    root, env = _repo(tmp_path, board)
    env[name] = "1"

    assert _push_with_semicolon(root, env) != 0


def test_the_procedure_names_the_gate_and_the_one_time_setting() -> None:
    """A hook nobody is told to configure does not exist in the next container."""

    section = _section("## 検証（省略不可）")

    assert section, "the mandatory-verification section is not where it was"
    assert "check_before_push.sh" in section
    assert "git config core.hooksPath .githooks" in section, (
        "the command itself - the paragraph below it also says the word, which "
        "is how a laxer check passed with the command deleted"
    )


def test_the_procedure_shows_a_join_that_carries_the_status() -> None:
    section = _section("## 検証（省略不可）")
    joins = [
        l for l in section.splitlines()
        if "check_before_push.sh" in l and "git push" in l
    ]

    assert joins, "the section has to show how the two are joined"
    for line in joins:
        assert "&&" in line, line
        assert ";" not in line, f"';' keeps nothing of the verdict: {line}"
        assert "|" not in line, f"a pipeline's status is the last command's: {line}"


def test_the_three_existing_commands_are_still_required() -> None:
    """禁じ手 ③: the gate is an addition, not a replacement."""

    section = _section("## 検証（省略不可）")

    for command in ("python -m pytest", "python scripts/verify_gate_recall.py",
                    "python scripts/product_metrics.py"):
        assert command in section, command
