"""A copy of the repository inside the repository must not be measured twice.

The tooling leaves git worktrees under ``.claude/worktrees/``. Each is a full
copy of the same files, and both of this project's corpus walkers used to
descend into them - so every document was counted once per copy.

That is not a small error in a small number. It moved the gate's
false-positive rate from 6.3% to 7.3% with **no document newly flagged**: the
count went 1,802 -> 4,011 and only the denominator had changed. A rate that
moves because of where somebody left a checkout is a rate nobody can act on,
and both the judge and the loops read these walkers.

Detection is structural rather than by name - a directory below the root
carrying its own ``.git`` is a separate checkout, whatever it is called and
wherever the tooling decides to put them next.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import measure_gate_baseline  # noqa: E402
import measure_outcomes  # noqa: E402


def _repository(root: Path) -> None:
    """A minimal checkout: a marker, a README and a document."""

    (root / ".git").mkdir()
    (root / "README.md").write_text("# 見出し\n本文。\n", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir()
    (docs / "plan.md").write_text(
        "# 計画\n収益化の方針について書いた文書。\n", encoding="utf-8"
    )


def _with_nested_copy(root: Path) -> None:
    """The same files again, under a worktree-shaped directory."""

    nested = root / ".claude" / "worktrees" / "agent-1"
    nested.mkdir(parents=True)
    # A worktree's `.git` is a file, not a directory - both shapes must count.
    (nested / ".git").write_text("gitdir: ../../../.git/worktrees/agent-1\n")
    (nested / "README.md").write_text("# 見出し\n本文。\n", encoding="utf-8")
    (nested / "docs").mkdir()
    (nested / "docs" / "plan.md").write_text(
        "# 計画\n収益化の方針について書いた文書。\n", encoding="utf-8"
    )


def test_the_gate_baseline_counts_the_repository_not_its_copies(tmp_path) -> None:
    _repository(tmp_path)
    alone = len(list(measure_gate_baseline.iter_documents(tmp_path, "owner/repo")))

    _with_nested_copy(tmp_path)
    with_copy = len(list(measure_gate_baseline.iter_documents(tmp_path, "owner/repo")))

    assert alone > 0, "the fixture must produce documents at all"
    assert with_copy == alone


def test_the_outcome_corpus_counts_the_repository_not_its_copies(tmp_path) -> None:
    """The copy is placed where this walker would otherwise descend.

    Under ``.claude/`` it never would - that path is not documentation-shaped,
    so this corpus excluded the tooling's usual location already, for an
    unrelated reason. Relying on that would leave the guard untested and the
    walker one relocated worktree away from the same fault the gate baseline
    actually suffered, so the checkout goes somewhere this walker does read.
    """

    _repository(tmp_path)
    alone = len(list(measure_outcomes.iter_files(tmp_path)))

    nested = tmp_path / "docs" / "checkout"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: ../../.git/worktrees/x\n")
    (nested / "docs").mkdir()
    (nested / "docs" / "plan.md").write_text(
        "# 計画\n収益化の方針について書いた文書。\n", encoding="utf-8"
    )

    with_copy = len(list(measure_outcomes.iter_files(tmp_path)))

    assert alone > 0
    assert with_copy == alone


def test_a_directory_that_merely_looks_nested_is_still_measured(tmp_path) -> None:
    """Only a checkout is skipped - an ordinary subdirectory is content."""

    _repository(tmp_path)
    before = len(list(measure_gate_baseline.iter_documents(tmp_path, "owner/repo")))

    ordinary = tmp_path / ".claude" / "worktrees" / "not-a-checkout"
    ordinary.mkdir(parents=True)
    (ordinary / "notes.md").write_text("# 覚え書き\n中身。\n", encoding="utf-8")

    after = len(list(measure_gate_baseline.iter_documents(tmp_path, "owner/repo")))
    assert after == before + 1
