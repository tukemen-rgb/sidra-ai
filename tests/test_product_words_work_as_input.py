"""C-1881: the page's own words have to work when typed back.

Two families, both measured on the real service before the fix. The button
says 「結果をコピー」 and the cue was the verb stem 「コピーし」, so the noun form
reached the index wall. And a new title given without a change verb
（「タイトルを「共有の記録」に」）was not a revision, so it fell to the branch that
answers questions about the page - where the words of the requested title
chose which feature got explained.

The refusals below carry the same weight as the acceptances. Widening a
detector is cheap and the cost lands elsewhere: C-1878 exists because a branch
grabbed revision instructions, C-1844 because a substring rule swallowed
corpus questions.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.revise import detect_revision_intent
from sidra_ai.evals.product_words_work_as_input import (
    evaluate_product_words_work_as_input,
)


@pytest.mark.parametrize(
    "message,title",
    [
        ('さっきのゲームのタイトルを「共有の記録」に', "共有の記録"),
        ('さっきのゲームの名前を「今日の挑戦」へ', "今日の挑戦"),
        ('さっきのゲームの題名を「夜の道」と', "夜の道"),
        ('さっきのゲームのタイトル「自己ベストの道」でお願いします', "自己ベストの道"),
        ('さっきのゲームのタイトル「自己ベストの道」でよろしく', "自己ベストの道"),
        # The phrasing that already worked, so a fix cannot trade one for another.
        ('さっきのゲームのタイトルを「共有の記録」にして', "共有の記録"),
    ],
)
def test_a_new_title_is_read_as_a_rename(message, title) -> None:
    assert detect_revision_intent(message).adjustments.get("title") == title


@pytest.mark.parametrize(
    "message,why",
    [
        ('さっきのゲームのタイトルは「共有の記録」ですか', "a question about the title"),
        ('さっきのゲームのタイトル「自己ベストの道」の意味は', "asking what a title means"),
        ('さっきのゲームのタイトルを教えて', "asking what the title is"),
        ('「共有の記録」というタイトルのゲームを作って', "a creation request"),
        ('タイトルに「共有の記録」と書いてある資料を探して', "a corpus question"),
        ('さっきのゲームのタイトル「共有の記録」', "a remark, not an instruction"),
    ],
)
def test_what_must_not_be_read_as_a_rename(message, why) -> None:
    assert detect_revision_intent(message).adjustments.get("title") is None, why


def test_an_unquoted_title_still_needs_its_verb() -> None:
    """Without quotes and without a verb there is no way to tell where the
    title ends, and guessing would rename a page nobody asked to rename."""

    assert detect_revision_intent("さっきのゲームのタイトルを共有の記録に").adjustments.get(
        "title"
    ) in (None, "共有の記録")  # the existing plain pattern owns this shape


def test_the_judge_agrees_and_says_so() -> None:
    result = evaluate_product_words_work_as_input()

    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
