"""C-1906: English "show me what you made" is answered with the list.

「show me what you made」「what have you made」 returned unrelated corpus fragments
because _ARTIFACT_LIST_QUERIES was Japanese-only. They now get an English
listing, while Japanese requests keep the Japanese one (rule 6). The English
sibling of C-1902 and C-1904.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.api.service import SidraService, _is_artifact_list_query
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_english_artifact_list_is_answered import (
    ENGLISH_LIST_QUERIES,
    NOT_A_LIST,
    evaluate_chat_english_artifact_list_is_answered,
)
from sidra_ai.ingestion.state import StateStore

_CJK = re.compile(r"[぀-ヿ㐀-鿿]")


@pytest.fixture()
def service(tmp_path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(tmp_path), model_backend="echo"),
        state_store=StateStore(tmp_path / "state.json"),
    )


def test_eval_passes():
    result = evaluate_chat_english_artifact_list_is_answered()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 14


@pytest.mark.parametrize("q", ENGLISH_LIST_QUERIES)
def test_english_list_recognised(q):
    assert _is_artifact_list_query(q), q


@pytest.mark.parametrize("q", NOT_A_LIST)
def test_corpus_question_not_a_list(q):
    assert not _is_artifact_list_query(q), q


def test_english_list_reply_is_english(service):
    service.chat("make a fishing game")
    r = service.chat("show me what you made")
    assert r["refusal"] == "artifact_list"
    assert not _CJK.search(r["answer"]) and "/v1/artifacts" in r["answer"]


def test_japanese_list_still_japanese(service):
    r = service.chat("作ったものを一覧で見せて")
    assert r["refusal"] == "artifact_list"
    assert _CJK.search(r["answer"])
