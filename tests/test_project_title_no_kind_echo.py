"""C-1277: the project bundle title drops the kind word.

「シューティングゲームの制作一式を作って」 came back
「『シューティングゲームの制作一式』の制作一式を…」 - 制作一式 twice. The title is
now the subject alone, like every other generator; a bare kind word still
produces a handled bundle with a fallback title.
"""

from __future__ import annotations

import tempfile

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.projects import _title_from
from sidra_ai.evals.project_title_no_kind_echo import (
    evaluate_project_title_no_kind_echo,
)


def _service() -> SidraService:
    return SidraService(Settings(data_dir=tempfile.mkdtemp(prefix="proj-title-test-")))


def test_project_title_no_kind_echo_eval_passes():
    result = evaluate_project_title_no_kind_echo()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4


def test_title_strips_the_kind_word():
    assert _title_from("シューティングゲームの制作一式を作って") == "シューティングゲーム"
    assert _title_from("忍者ゲームのプロジェクト一式を作って") == "忍者ゲーム"
    assert _title_from("レースゲーム制作一式を作って") == "レースゲーム"
    # bare kind word falls back to the default, not an empty title
    assert _title_from("制作一式を作って") == "無題のゲーム"


def test_summary_does_not_double_echo_the_kind_word():
    answer = _service().chat("シューティングゲームの制作一式を作って")["answer"]
    assert "「シューティングゲーム」の制作一式を" in answer
    assert "シューティングゲームの制作一式」" not in answer
