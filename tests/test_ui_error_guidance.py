"""C-1211: a failed request explains itself instead of naming a number.

「失敗: HTTP 422」 gave an operator nothing to act on. The page now maps
the reachable failure classes to Japanese guidance with the code kept in
parentheses; the response body remains unread, which is the privacy line
the original design drew.
"""

from __future__ import annotations

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_error_guidance import evaluate_ui_error_guidance


def test_reachable_failure_classes_have_guidance():
    assert "アクセストークンを確認してください" in ASK_PAGE
    assert "入力が長すぎるか形式が不正です" in ASK_PAGE
    assert "混み合っています" in ASK_PAGE
    assert "サーバ側で問題が起きました" in ASK_PAGE


def test_every_throw_site_uses_the_map():
    assert ASK_PAGE.count("explain(response.status)") >= 5
    assert 'Error("HTTP " + response.status)' not in ASK_PAGE


def test_the_code_is_still_printed():
    assert "（HTTP " in ASK_PAGE


def test_ui_error_guidance_eval_passes():
    result = evaluate_ui_error_guidance()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6
