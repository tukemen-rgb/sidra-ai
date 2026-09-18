"""C-1943: the timestamp gate must judge even when a merge is in the range.

The lock, not the repair - ``errors="replace"`` was already on main. What
this pins is that the lock fails when the repair is undone, which took three
fixtures to achieve: the first never completed its conflicted merge, the
second let an ASCII filler win git's funcname pick. Both scored full marks
with the decode bug fully restored.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from sidra_ai.evals.gate_checks_after_a_merge import (
    evaluate_gate_checks_after_a_merge,
)

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_log_times.py"


def _load():
    spec = importlib.util.spec_from_file_location("_merge_gate_under_test", CHECK)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_merge_gate_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_all_four_cases_hold():
    result = evaluate_gate_checks_after_a_merge()
    assert result.checks_passed == 4, result.failures
    assert result.passed


def test_git_is_read_without_strict_decoding():
    """The one line that was the bug. A combined diff is not always valid
    UTF-8 because the hunk header truncates the enclosing line by bytes."""

    assert 'errors="replace"' in CHECK.read_text(encoding="utf-8")


def test_a_broken_gate_says_so_instead_of_refusing():
    """禁じ手 (5): a breakdown must not wear a refusal's face. Exit 2 is
    'could not check', matching the other pre-push checks."""

    text = CHECK.read_text(encoding="utf-8")
    assert "COULD NOT CHECK" in text
    assert "return 2" in text


def test_the_real_merge_still_decodes_through_this_path():
    """Measured against the merge the item was filed on, if it is reachable.

    Skipped rather than asserted away when the history is not present, so a
    shallow clone does not turn a missing measurement into a pass.
    """

    import pytest

    known = subprocess.run(
        ["git", "cat-file", "-e", "22eebaae^{commit}"], cwd=ROOT, capture_output=True
    )
    if known.returncode != 0:
        pytest.skip("the merge this was filed on is not in this clone")

    check = _load()
    shown = check._git(
        "show", "--format=", "--unified=0", "22eebaae", "--", "docs/LOOP_LOG.md"
    )
    assert shown.returncode == 0
    assert len(shown.stdout) > 0, "the path that used to raise now returns text"


def test_this_tree_passes_its_own_gate():
    done = subprocess.run(
        [sys.executable, str(CHECK)], cwd=ROOT, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout + done.stderr
