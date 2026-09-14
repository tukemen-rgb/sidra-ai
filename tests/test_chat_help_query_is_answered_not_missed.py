"""C-1802: a help/meta question gets an overview, not a corpus-miss abstention.

「使い方を教えて」「何ができる」「ヘルプ」 now return refusal=="help" with a reply
that says what SIDRA does, not the no-evidence abstention. A real question, or one
that only contains 「使い方」, is unaffected.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_help_query_is_answered_not_missed import (
    evaluate_chat_help_query_is_answered_not_missed,
)


@pytest.fixture
def service(tmp_path) -> SidraService:
    return SidraService(Settings(data_dir=str(tmp_path / "sidra")))


def test_help_query_eval_passes():
    result = evaluate_chat_help_query_is_answered_not_missed()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_a_help_question_is_answered_with_an_overview(service: SidraService):
    reply = service.chat("使い方を教えて")
    assert reply["refusal"] == "help"
    assert "索引済みリポジトリ" in reply["answer"]
    assert "現時点では十分な根拠がありません" not in reply["answer"]
    assert "/v1/github/analyze" not in reply["answer"]


def test_what_can_you_do_is_help(service: SidraService):
    assert service.chat("何ができる")["refusal"] == "help"


def test_a_real_question_is_not_help(service: SidraService):
    assert service.chat("火星の天気を教えて")["refusal"] != "help"


def test_a_query_that_only_contains_the_word_is_not_help(service: SidraService):
    assert service.chat("使い方のドキュメントを探して")["refusal"] != "help"
