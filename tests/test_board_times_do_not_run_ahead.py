"""C-1914: a line may not claim a time it has not reached.

The margin this pins is small because of a mechanism, not a percentile:
`date -u` floors to the minute and the commit happens after the writing,
so an honestly written line's lead is never positive. The number it
replaced was measured off the leading lines themselves.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sidra_ai.evals.board_times_do_not_run_ahead import (
    evaluate_board_times_do_not_run_ahead,
)

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_log_times.py"


def _load():
    spec = importlib.util.spec_from_file_location("_times_under_test", CHECK)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_times_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_all_four_cases_hold():
    result = evaluate_board_times_do_not_run_ahead()
    assert result.checks_passed == 4, result.failures
    assert result.passed


def test_the_margin_is_not_taken_from_the_lines_it_judges():
    """30 minutes came from "+20.2 is the honest lag", and +20.2 was a
    violation. Anything that wide re-admits what the check exists for."""

    assert 0 <= _load().MARGIN_MINUTES <= 1


def test_a_short_history_is_unmeasurable_not_zero():
    """C-1723: a census that read nothing must not look like health."""

    check = _load()
    assert check.CENSUS_NEEDS_COMMITS > 0
    assert check.census.__doc__ and "None" in check.census.__doc__


def test_the_census_reads_this_repository():
    """And on a real history it returns counts rather than None."""

    seen = _load().census()
    assert seen is not None, "this repository has enough history to be read"
    assert seen["lines_read"] > 0
    assert seen["ahead_minute_or_more"] <= seen["lines_read"]


def test_the_refusal_says_what_would_pass():
    """禁じ手 (5): tightening is the point, so the refusal has to name the
    one thing that makes a line honest - reading the clock as you write."""

    text = CHECK.read_text(encoding="utf-8")
    assert "date -u" in text
    assert "直し方" in text


def test_the_hidden_minute_is_still_read_as_a_lower_bound():
    """禁じ手 (4): 「13:4x」 must keep meaning the earliest minute it can."""

    text = CHECK.read_text(encoding="utf-8")
    assert 'replace("x", "0")' in text
