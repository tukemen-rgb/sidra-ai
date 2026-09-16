"""C-1886: plain_text strips *** / ___ horizontal rules (C-1695/C-1709 family)."""

from __future__ import annotations

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.plain_text_strips_horizontal_rule import (
    evaluate_plain_text_strips_horizontal_rule,
)


def test_eval_passes():
    result = evaluate_plain_text_strips_horizontal_rule()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_star_rule_removed():
    out = plain_text("A\n\n***\n\nB")
    assert "*" not in out and "A" in out and "B" in out


def test_underscore_rule_removed():
    out = plain_text("A\n\n___\n\nB")
    assert "___" not in out and "A" in out and "B" in out


def test_emphasis_not_over_stripped():
    assert "重要" in plain_text("これは *重要* です")
    assert "設定" in plain_text("これは __設定__ です")


def test_midline_star_kept():
    assert "3 * 4" in plain_text("面積は 3 * 4 = 12 です。")
