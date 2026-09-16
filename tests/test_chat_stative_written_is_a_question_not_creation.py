"""C-1899: 「どこに書いてある？」 is a question, not a request to write.

The te-form 「書いて」 matched as a substring inside the stative 「書いてある/
書いている」 ("is written"), so a plain question routed to creation and got
「制作のご依頼と受け取りましたが、この形式は作れません」. The stative forms are now
neutralised before the make-verb scan, without touching a genuine 「…を書いて」.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.chat_stative_written_is_a_question_not_creation import (
    GENUINE_MAKE,
    STATIVE_QUESTIONS,
    evaluate_chat_stative_written_is_a_question_not_creation,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_stative_written_is_a_question_not_creation()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 14


@pytest.mark.parametrize("phrase", STATIVE_QUESTIONS)
def test_stative_is_not_creation(phrase):
    assert not detect_creation_intent(phrase).is_creation, phrase


@pytest.mark.parametrize("phrase", GENUINE_MAKE)
def test_genuine_write_is_still_creation(phrase):
    assert detect_creation_intent(phrase).is_creation, phrase


def test_stative_question_reaches_answer_not_creation_refusal(service):
    ans = service.chat("設定はどこに書いてある")["answer"]
    assert "制作のご依頼" not in ans and "この形式は作れません" not in ans


def test_genuine_write_still_makes(service):
    result = service.chat("レポートを書いて")
    assert result.get("creation") or "作りました" in (result.get("answer") or "")
