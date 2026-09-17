"""C-1917: whereabouts questions about the user's own artifacts are answered.

「作ったファイルはどこにありますか」 / "where are my files" / "list my files"
fell to RAG and returned an unrelated corpus document. They now reach the
artifact-list handler, which names where the files are (/v1/artifacts). A corpus
question about some files and the download-ambiguous phrasing are not swallowed.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import _is_artifact_list_query
from sidra_ai.evals.chat_where_are_my_files_is_answered import (
    LOCATION_QUERIES,
    NOT_LOCATION_QUERIES,
    evaluate_chat_where_are_my_files_is_answered,
)


def test_eval_passes():
    result = evaluate_chat_where_are_my_files_is_answered()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 15


@pytest.mark.parametrize("query", LOCATION_QUERIES)
def test_location_query_is_recognized(query):
    assert _is_artifact_list_query(query) is True


@pytest.mark.parametrize("query", NOT_LOCATION_QUERIES)
def test_corpus_or_download_question_is_not_swallowed(query):
    assert _is_artifact_list_query(query) is False
