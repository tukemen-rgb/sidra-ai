"""C-1915: an English delete request gets the honest delete_unsupported refusal.

"delete the game" / "delete it" / "remove the last game" fell through to RAG and
returned an unrelated indexed document; 「消して」 got the honest refusal (C-1847).
An English delete pattern plus a language-branched reply (rule 6) fix it. The
boundary stays tight: a corpus question about deletion and a feature request are
not deletions of an artifact.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.revise import asks_to_delete
from sidra_ai.evals.chat_english_delete_says_it_cannot import (
    DELETE_REQUESTS_EN,
    NOT_DELETIONS_EN,
    evaluate_chat_english_delete_says_it_cannot,
)


def test_eval_passes():
    result = evaluate_chat_english_delete_says_it_cannot()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 17


@pytest.mark.parametrize("message", DELETE_REQUESTS_EN)
def test_english_delete_is_recognized(message):
    assert asks_to_delete(message) is True


@pytest.mark.parametrize("message", NOT_DELETIONS_EN)
def test_non_deletion_is_not_recognized(message):
    assert asks_to_delete(message) is False


@pytest.mark.parametrize("message", [
    "how does soft-delete work",
    "the delete button removes a row",
    "delete a column from the table",
    "remove the deprecated dependency",
])
def test_corpus_deletion_questions_are_not_caught(message):
    # A question or statement about deletion in the code is not a request to
    # delete an artifact; it must keep reaching the corpus.
    assert asks_to_delete(message) is False


def test_japanese_delete_still_recognized():
    assert asks_to_delete("さっきのゲームを消して") is True
