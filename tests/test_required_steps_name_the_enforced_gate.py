"""C-1824: the mandatory-verification section names the check that fails builds.

It told a loop touching a detector to re-measure with ``measure_gate_baseline.py``
against 「現在の基準値は 1012 文書中 3.5%」 - a 2026-08-18 reading of a corpus
that has since grown two and a half times - and never mentioned
``check_gate_regression.py``, which CI runs every time and which enforces the
two ceilings mechanically.

Each rule is pinned by doctoring a copy and showing it go to 0. The doctoring
is scoped to the section, because the board mentions the gate 16 times
elsewhere and a whole-file test would pass on a section that says nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.evals.required_steps_name_the_enforced_gate import (
    _section,
    evaluate_required_steps_name_the_enforced_gate,
)

_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def board() -> str:
    return (_ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")


@pytest.fixture
def baseline() -> str:
    return (_ROOT / "docs" / "GATE_FALSE_POSITIVE_BASELINE.md").read_text(encoding="utf-8")


def _doctor(board: str, old: str, new: str) -> str:
    """Rewrite only inside 「検証（省略不可）」."""

    section = _section(board)
    assert old in section, old
    return board.replace(section, section.replace(old, new))


def test_the_live_documents_pass() -> None:
    result = evaluate_required_steps_name_the_enforced_gate()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total


def test_the_section_must_name_the_gate_itself_not_the_file(board, baseline) -> None:
    doctored = _doctor(board, "check_gate_regression.py", "（ある検査）")
    # The rest of the board still mentions it many times over.
    assert doctored.count("check_gate_regression.py") > 5
    assert not evaluate_required_steps_name_the_enforced_gate(doctored, baseline).passed


@pytest.mark.parametrize("ceiling", ["13.0%", "20.0%"])
def test_each_enforced_ceiling_must_be_written_down(board, baseline, ceiling) -> None:
    doctored = _doctor(board, ceiling, "十分低い値")
    assert not evaluate_required_steps_name_the_enforced_gate(doctored, baseline).passed


def test_the_old_reading_may_not_be_called_current_again(board, baseline) -> None:
    doctored = _doctor(board, "「現在の」値ではない", "現在の基準値である")
    assert not evaluate_required_steps_name_the_enforced_gate(doctored, baseline).passed


def test_the_old_reading_may_not_be_deleted_either(board, baseline) -> None:
    # 禁じ手 ①: 3.5% is a real measurement. "Not called current" must not be
    # satisfiable by removing it.
    assert not evaluate_required_steps_name_the_enforced_gate(
        board.replace("3.5%", "（削除）"), baseline.replace("3.5%", "（削除）")
    ).passed
