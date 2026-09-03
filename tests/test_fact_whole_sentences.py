"""C-1213: generator-bound excerpts end at a sentence, not mid-word.

The excerpt window starts at a line boundary but ended at a hard character
cap, so bullets read 「…予約投」. The trim cuts back to the last terminator
and refuses to trim when that would leave less than the minimum - a
fragment with content beats an empty polish. The /v1/chat citation
excerpts stay raw for byte-for-byte source review.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import _MIN_TRIMMED, whole_sentences
from sidra_ai.evals.fact_whole_sentences import evaluate_fact_whole_sentences

_LONG = (
    "掲載実績は 21,907 件で、紹介サイトとして国内最大級の規模になっている。"
    "事前に本人へ一言を徹底する運用も既に定着した。"
)


def test_dangling_tail_is_cut_at_the_last_sentence():
    assert whole_sentences(_LONG + "予約投") == _LONG


def test_terminator_free_text_passes_through():
    text = "文末が全く無い断片テキストがそのまま残ること"
    assert whole_sentences(text) == text


def test_a_head_only_terminator_does_not_gut_the_excerpt():
    text = "短い。" + "だ" * (_MIN_TRIMMED)
    assert whole_sentences(text) == text


def test_never_widens_only_trims():
    assert len(whole_sentences(_LONG + "予約投")) <= len(_LONG + "予約投")


def test_fact_whole_sentences_eval_passes():
    result = evaluate_fact_whole_sentences()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4
