"""C-1228: a 404 on the download path must say what to do next.

Clicking 開く on a generated file removed or renamed since the list returns
404, and the catch showed 「ダウンロードに失敗: HTTP 404」 - a bare code.
``explain`` now maps 404 to 「見つかりません。一覧を更新してください（…）」,
with the code still printed and the pre-existing classes unchanged.
"""

from __future__ import annotations

import re

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_missing_artifact_guidance import (
    evaluate_ui_missing_artifact_guidance,
)


def test_ui_missing_artifact_guidance_eval_passes():
    result = evaluate_ui_missing_artifact_guidance()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_explain_has_404_branch_before_fallthrough():
    assert re.search(r"status\s*===\s*404", ASK_PAGE)
    assert "見つかりません" in ASK_PAGE and "一覧を更新" in ASK_PAGE
    assert ASK_PAGE.index("status === 404") < ASK_PAGE.index("return why ?")


def test_preexisting_error_classes_kept():
    assert "アクセストークンを確認してください" in ASK_PAGE
    assert "サーバ側で問題が起きました" in ASK_PAGE
    assert "（HTTP " in ASK_PAGE
