"""The line that wires the gate belongs where a loop reads it first (C-1807).

C-1794 put ``.githooks/pre-push`` in the repository and the one-time
``git config core.hooksPath .githooks`` into 「検証（省略不可）」. Its own
filing said hooks do not travel with a clone - and six hours later an
inconsistent board reached ``main`` again with the gate in place.

**Why that push got through was never established**, and this file does not
claim to know: another container's git config is not visible from here. What is
measurable is where the instruction lives, and what an unwired copy is told.

The placement is the whole point. 手順 0 is the one section every loop reads
**before starting work**; 「検証（省略不可）」 is read when it is time to
verify - by which point the copy has already been used. Wiring is startup work.

And the notice is a notice. Running the gate by hand is a proper use, including
while setting a copy up, so an unwired copy is told and then allowed through
(禁じ手 ①).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "docs" / "BACKLOG.md"
WIRE = "git config core.hooksPath .githooks"


def _section(heading: str) -> str:
    lines = BOARD.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith(heading):
            rest = lines[i + 1:]
            end = next((j for j, l in enumerate(rest) if l.startswith("## ")), len(rest))
            return "\n".join(rest[:end])
    return ""


def _copy(home: Path, wire: bool) -> tuple[int, str]:
    """A working copy of the gate, wired to git or not. Returns (rc, output)."""

    root = home / "work"
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""), "HOME": str(home),
    }
    (root / "scripts").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / ".githooks").mkdir()
    (root / "src" / "sidra_ai" / "evals").mkdir(parents=True)
    for name in ("check_before_push.sh", "check_log_times.py",
                 "check_eval_scratch.py", "check_backlog_board.py",
                 "check_numbers_upstream.py", "check_metric_names.py"):
        shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
    shutil.copy2(ROOT / ".githooks" / "pre-push", root / ".githooks" / "pre-push")
    (root / ".githooks" / "pre-push").chmod(0o755)
    (root / "src" / "sidra_ai" / "evals" / "scratch.py").write_text(
        '"""h"""\n\n\ndef scratch_dir(prefix=""):\n    return "/tmp"\n', encoding="utf-8")
    (root / "src" / "sidra_ai" / "evals" / "one.py").write_text(
        "from sidra_ai.evals.scratch import scratch_dir\n\n\n"
        "def go():\n    return scratch_dir()\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (root / "docs" / "BACKLOG.md").write_text(
        "# board\n\n- [ ] **C-0001: base.**\n", encoding="utf-8")
    (root / "docs" / "LOOP_LOG.md").write_text("# log\n", encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, env=env, check=True,
                       capture_output=True, timeout=180)

    git("init", "-q", "-b", "main"); git("add", "-A"); git("commit", "-q", "-m", "base")
    if wire:
        git("config", "core.hooksPath", ".githooks")
    done = subprocess.run(["bash", "scripts/check_before_push.sh"], cwd=root,
                          env=env, capture_output=True, text=True, timeout=300)
    return done.returncode, done.stdout


def test_the_startup_section_carries_the_wiring() -> None:
    """手順 0 is read before work. 「検証（省略不可）」 is read after the copy
    has already been used, which is why C-1794's placement was not enough."""

    startup = _section("## 手順 0")

    assert startup, "the startup section is not where it was"
    assert WIRE in startup


def test_the_verification_section_still_carries_it_too() -> None:
    """C-1794's line is not moved, only joined: a loop that reaches
    verification without having wired anything should still be told."""

    assert WIRE in _section("## 検証（省略不可）")


def test_an_unwired_copy_is_told(tmp_path: Path) -> None:
    rc, said = _copy(tmp_path, wire=False)

    assert "core.hooksPath is unset" in said
    assert WIRE in said, "a notice without the remedy is half a notice"


def test_being_unwired_is_not_a_refusal(tmp_path: Path) -> None:
    """禁じ手 ①. Running the gate by hand is a proper use - including while
    setting a copy up - so it must pass."""

    rc, said = _copy(tmp_path, wire=False)

    assert rc == 0, said
    assert "OK to push" in said


def test_a_wired_copy_is_not_nagged(tmp_path: Path) -> None:
    """A notice that fires every time is one nobody reads."""

    rc, said = _copy(tmp_path, wire=True)

    assert rc == 0, said
    assert "core.hooksPath is unset" not in said


def test_a_hooks_path_without_a_hook_is_also_told(tmp_path: Path) -> None:
    """Set but pointing nowhere is the same silence as unset: git runs no
    check either way."""

    root = tmp_path / "work"
    rc, _ = _copy(tmp_path, wire=True)
    assert rc == 0
    (root / ".githooks" / "pre-push").unlink()
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)}
    done = subprocess.run(["bash", "scripts/check_before_push.sh"], cwd=root,
                          env=env, capture_output=True, text=True, timeout=300)

    assert "no executable pre-push hook" in done.stdout
    assert done.returncode == 0, "still a notice, not a refusal"
