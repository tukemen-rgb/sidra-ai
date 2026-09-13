"""C-1777: a shared daily line discloses an adapt auto-ease.

The daily stamp claims a challenge everybody got. C-1768 disclosed hand-set
tuning; adapt's auto-ease (three losses buy one easier rung, applied at load by
adaptSpeed) was the other runtime source of a diverged board and went unnamed.
shareText now adds 「難度自動緩和」 when ADAPT_EASED, while a clean daily, a
manual-tuned daily, and a private eased board are unaffected.
"""

from __future__ import annotations

import shutil

import pytest

from sidra_ai.evals.share_daily_discloses_auto_ease import (
    _TEMPLATE,
    _line,
    evaluate_share_daily_discloses_auto_ease,
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to play the page"
)

_MARK = "難度自動緩和"
_STAMP = "2026-09-03"
_KEY = f"sidra.streak.{_TEMPLATE}"


def test_share_auto_ease_eval_passes():
    result = evaluate_share_daily_discloses_auto_ease()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_eased_daily_is_disclosed():
    line = _line({f"sidra.tune.{_TEMPLATE}": {"daily": True}, _KEY: "3"})
    assert _STAMP in line and "今日の" in line
    assert _MARK in line


def test_clean_daily_makes_no_such_claim():
    line = _line({f"sidra.tune.{_TEMPLATE}": {"daily": True}})
    assert _STAMP in line
    assert _MARK not in line


def test_private_eased_board_carries_no_daily_or_ease_claim():
    line = _line({_KEY: "3"})
    assert _STAMP not in line and _MARK not in line
