"""C-1901: identity/help questions are answered, not sent to the index wall.

「あなたは誰？」「助けて」「どう使うの？」 and their kin reached the no-evidence
abstention that asks for a repository to be ingested. They now route to the help
reply. It stays a whole-message match, so a real corpus query that merely
contains 「使い方」/「何」 is untouched (C-1796/C-1802 family).
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SidraService, _is_help_query
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_identity_and_help_questions_are_answered import (
    IDENTITY_HELP_QUESTIONS,
    NOT_HELP_QUESTIONS,
    evaluate_chat_identity_and_help_questions_are_answered,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_identity_and_help_questions_are_answered()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 17


@pytest.mark.parametrize("phrase", IDENTITY_HELP_QUESTIONS)
def test_identity_help_is_recognised(phrase):
    assert _is_help_query(phrase), phrase


@pytest.mark.parametrize("phrase", NOT_HELP_QUESTIONS)
def test_corpus_question_is_not_help(phrase):
    assert not _is_help_query(phrase), phrase


def test_identity_question_reaches_help_reply(service):
    result = service.chat("あなたは誰？")
    assert result["refusal"] == "help"
    assert "十分な根拠がありません" not in result["answer"]


def test_corpus_question_is_not_answered_as_help(service):
    assert service.chat("認証の使い方を教えて").get("refusal") != "help"
