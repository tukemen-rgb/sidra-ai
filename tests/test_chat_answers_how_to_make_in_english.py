"""C-1921: English how-to-make questions are answered, not walled.

"how do I make a report" / "how do I create a game" fell to the RAG wall while
「レポートの作り方を教えて」 got the how_to_make reply. English cues + kind
keywords + a language-branched answer close the gap; a corpus question naming a
source ("...from the docs") and a cue with no kind stay out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService, _how_to_make_kinds
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_answers_how_to_make_in_english import (
    ENGLISH_HOW_TO,
    NOT_HOW_TO,
    evaluate_chat_answers_how_to_make_in_english,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_answers_how_to_make_in_english()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize("question", ENGLISH_HOW_TO)
def test_english_how_to_is_answered_in_english(service, question):
    r = service.chat(question)
    assert r["refusal"] == "how_to_make"
    answer = r["answer"]
    assert "作れます" not in answer
    assert "/v1/github/analyze" not in answer
    assert "I can make" in answer


@pytest.mark.parametrize("question", NOT_HOW_TO)
def test_non_how_to_is_not_caught(service, question):
    assert _how_to_make_kinds(question, service.creation_router.registered_kinds()) == ()


def test_japanese_how_to_still_answered(service):
    assert service.chat("レポートの作り方を教えて")["refusal"] == "how_to_make"
