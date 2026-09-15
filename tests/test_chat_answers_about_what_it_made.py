"""C-1866: a question about the page it just made gets an answer.

Six phrasings, one turn after 「魚釣りゲームを作って」, all reached the abstention
that asks for a repository to be ingested - about features that page ships.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import _feature_topics
from sidra_ai.creation.ghost import GHOST_TEMPLATES
from sidra_ai.evals.chat_answers_about_what_it_made import (
    CORPUS_QUESTIONS,
    FEATURE_QUESTIONS,
    evaluate_chat_answers_about_what_it_made,
)


def test_answers_about_what_it_made_eval_passes():
    result = evaluate_chat_answers_about_what_it_made()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 14


@pytest.mark.parametrize("question", FEATURE_QUESTIONS)
def test_a_question_about_the_page_is_recognised(question):
    assert _feature_topics(question)


@pytest.mark.parametrize("question", CORPUS_QUESTIONS)
def test_a_question_that_names_a_source_is_a_corpus_question(question):
    """Naming where to look makes it a corpus question, whatever else it says.

    Measured while writing the rule: 「共有ポリシーについてドキュメントから探して」
    was swallowed by the 「共有」 cue. C-1844 avoided this by matching whole
    messages; matching substrings here is what makes the veto necessary.
    """

    assert not _feature_topics(question)


def test_the_veto_is_about_sources_not_about_asking():
    """「教えて」 is also how somebody asks about their own page.

    A verb veto would have closed the door this item exists to open.
    """

    assert _feature_topics("共有のやり方を教えて")
    assert not _feature_topics("資料の共有について教えて")


def test_the_ghost_belongs_to_three_templates():
    """The fixture's premise, asserted so it cannot rot quietly."""

    assert "fishing" not in GHOST_TEMPLATES
    assert "racing" in GHOST_TEMPLATES
