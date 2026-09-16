"""C-1904: English help/identity questions are answered, not sent to the wall.

「What can you do?」「who are you?」「how do I use this?」 returned unrelated corpus
fragments because _HELP_QUERIES was Japanese-only. They now get an English help
reply, while Japanese help questions keep the Japanese one (rule 6). The English
sibling of C-1901 and C-1902.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.chat_english_help_questions_are_answered import (
    ENGLISH_HELP_QUESTIONS,
    NOT_HELP,
    evaluate_chat_english_help_questions_are_answered,
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
    result = evaluate_chat_english_help_questions_are_answered()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 14


@pytest.mark.parametrize("q", ENGLISH_HELP_QUESTIONS)
def test_english_help_gets_english_reply(service, q):
    r = service.chat(q)
    assert r["refusal"] == "help"
    answer = r["answer"]
    assert re.search(r"[A-Za-z]", answer) and not _CJK.search(answer)
    assert "/v1/github/analyze" not in answer


def test_japanese_help_still_japanese(service):
    r = service.chat("何ができる")
    assert r["refusal"] == "help"
    assert "索引済みリポジトリについてお答えします" in r["answer"]


@pytest.mark.parametrize("q", NOT_HELP)
def test_real_corpus_question_not_help(service, q):
    assert service.chat(q).get("refusal") != "help"
