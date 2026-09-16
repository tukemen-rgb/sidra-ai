"""C-1897: "show me what I made", said naturally, reaches the list.

``_is_artifact_list_query`` matched the whole message against a fixed set, so
「作ったものの一覧を見せて」 (the set's own 「作ったものの一覧」 + the request
「を見せて」) fell through to corpus retrieval and answered with an unrelated
document. A trailing request verb is now stripped before the match, so a
composed phrase reduces to a base the set knows - without a substring rule that
would swallow a real corpus query.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import SidraService, _is_artifact_list_query
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_lists_made_things_for_natural_phrasing import (
    NATURAL_LIST_PHRASINGS,
    NOT_LIST_PHRASINGS,
    evaluate_chat_lists_made_things_for_natural_phrasing,
)
from sidra_ai.ingestion.state import StateStore


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_lists_made_things_for_natural_phrasing()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 19


@pytest.mark.parametrize("phrase", NATURAL_LIST_PHRASINGS)
def test_natural_phrasings_are_recognised(phrase):
    assert _is_artifact_list_query(phrase), phrase


@pytest.mark.parametrize("phrase", NOT_LIST_PHRASINGS)
def test_corpus_questions_are_not_a_list_request(phrase):
    assert not _is_artifact_list_query(phrase), phrase


def test_a_natural_phrasing_reaches_the_list_end_to_end(service):
    result = service.chat("作ったものの一覧を見せて")
    assert result["refusal"] == "artifact_list"
    assert "まだ何も作っていません" in result["answer"]


def test_a_close_corpus_query_still_reaches_retrieval(service):
    result = service.chat("作ったものの一覧をドキュメントから探して")
    assert result.get("refusal") != "artifact_list"
