"""C-1261: an unbuildable make request is declined honestly, not sent to Q&A.

「Excelを作って」「アプリを作って」were read as creation (kind=UNKNOWN, weak) but
fell through to the Q&A no-evidence wall because the service only routed strong
intents. Now they get an honest decline listing what can be made, while a
buildable request still creates and a real question still reaches Q&A.
"""

from __future__ import annotations

import tempfile

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.creation_unbuildable_declined import (
    evaluate_creation_unbuildable_declined,
)


def _service() -> SidraService:
    return SidraService(Settings(data_dir=tempfile.mkdtemp(prefix="unbuildable-test-")))


def test_creation_unbuildable_declined_eval_passes():
    result = evaluate_creation_unbuildable_declined()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 12


def test_unbuildable_request_is_declined_with_kinds():
    svc = _service()
    answer = svc.chat("Excelを作って")["answer"]
    assert "作れません" in answer
    assert "作れるのは" in answer
    # Lists real buildable kinds, not the Q&A ingestion wall.
    assert "ゲーム" in answer and "レポート" in answer
    assert "/v1/github/analyze" not in answer


def test_buildable_request_still_creates():
    svc = _service()
    answer = svc.chat("レースゲームを作って")["answer"]
    assert "作りました" in answer
    assert "作れません" not in answer


def test_question_still_reaches_question_path():
    svc = _service()
    answer = svc.chat("GAMEYARDの理念を教えて")["answer"]
    # Empty corpus -> the honest no-evidence answer, not the creation decline.
    assert "作れません" not in answer
