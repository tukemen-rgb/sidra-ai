"""C-1795: a bare greeting gets a friendly reply, not a corpus-miss abstention.

「こんにちは」「ありがとう」 alone are not questions; chat now returns a
greeting refusal (refusal=="greeting") with a friendly answer that does not
name the ingest endpoint, while a greeting that opens a real question is still
answered as the question.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_greeting_is_greeted_not_missed import (
    evaluate_chat_greeting_is_greeted_not_missed,
)
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

_REPO = "tukemen-rgb/sidra-ai"


@pytest.fixture
def service(tmp_path) -> SidraService:
    settings = Settings(allowed_repositories=(_REPO,), data_dir=str(tmp_path / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(_REPO,),
        quarantine_store=QuarantineStore(tmp_path / "q.jsonl"),
    )
    return SidraService(settings, store=DocumentStore(gate), gate=gate)


def test_greeting_eval_passes():
    result = evaluate_chat_greeting_is_greeted_not_missed()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_bare_greeting_is_greeted(service: SidraService):
    reply = service.chat("こんにちは")
    assert reply["refusal"] == "greeting"
    assert "現時点では十分な根拠がありません" not in reply["answer"]
    assert "/v1/github/analyze" not in reply["answer"]


def test_thanks_with_punctuation_is_greeted(service: SidraService):
    assert service.chat("ありがとうございます。")["refusal"] == "greeting"


def test_a_real_question_is_not_a_greeting(service: SidraService):
    assert service.chat("サイトのリポジトリについて教えて")["refusal"] != "greeting"


def test_a_greeting_prefixed_question_stays_a_question(service: SidraService):
    assert service.chat("こんにちは、売上を教えて")["refusal"] != "greeting"
