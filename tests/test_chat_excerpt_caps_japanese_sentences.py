"""C-1517: the chat excerpt must cap Japanese sentences like English.

``_lead`` split on whitespace after a terminator, which Japanese omits after
「。」, so a Japanese block counted as one sentence and the two-sentence cap
never fired. Boundaries are now found by position; a CJK terminator ends a
sentence on its own.
"""

from __future__ import annotations

from sidra_ai.evals.chat_excerpt_caps_japanese_sentences import (
    evaluate_chat_excerpt_caps_japanese_sentences,
)
from sidra_ai.models.echo import EchoModelAdapter


def test_excerpt_cap_eval_passes():
    result = evaluate_chat_excerpt_caps_japanese_sentences()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_japanese_excerpt_stops_at_two_sentences():
    lead = EchoModelAdapter()._lead(
        "第一文は十分に長い説明の文章です。第二文も十分に長い説明の文章です。"
        "第三文は現れてはいけない内容です。"
    )
    assert "第一文" in lead and "第二文" in lead
    assert "第三文" not in lead
    # No space is inserted between Japanese sentences that had none.
    assert "。 " not in lead


def test_english_excerpt_cap_unchanged():
    lead = EchoModelAdapter()._lead(
        "First sentence long enough to count. "
        "Second sentence also long enough to count. "
        "Third must not appear in the lead."
    )
    assert lead == (
        "First sentence long enough to count. "
        "Second sentence also long enough to count."
    )


def test_ascii_decimal_is_not_a_sentence_boundary():
    lead = EchoModelAdapter()._lead(
        "速度は3.5倍に向上した実測の結果です。次の目標は10倍の高速化になります。"
        "三つ目の文は出てはいけません。"
    )
    assert "3.5倍" in lead
    assert "三つ目" not in lead
