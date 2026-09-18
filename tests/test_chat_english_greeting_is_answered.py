"""C-1902: an English greeting is answered, not sent to the index wall.

「hello」/「thanks」 fell to the English no-evidence abstention ("...POST
/v1/github/analyze"). They now get an English greeting reply, while Japanese
greetings keep the Japanese one (rule 6). The English twin of C-1796.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_english_greeting_is_answered import (
    ENGLISH_GREETINGS,
    NOT_A_GREETING,
    evaluate_chat_english_greeting_is_answered,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_english_greeting_is_answered()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 13


@pytest.mark.parametrize("greeting", ENGLISH_GREETINGS)
def test_english_greeting_gets_english_reply(service, greeting):
    r = service.chat(greeting)
    assert r["refusal"] == "greeting"
    answer = r["answer"]
    assert re.search(r"[A-Za-z]", answer)
    assert "十分な根拠がありません" not in answer
    assert "/v1/github/analyze" not in answer
    assert "ご挨拶" not in answer


def test_japanese_greeting_still_japanese(service):
    r = service.chat("こんにちは")
    assert r["refusal"] == "greeting"
    assert "ご挨拶" in r["answer"]


@pytest.mark.parametrize("q", NOT_A_GREETING)
def test_real_question_not_swallowed(service, q):
    assert service.chat(q).get("refusal") != "greeting"
