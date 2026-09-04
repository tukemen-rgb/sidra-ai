"""C-1231: answer language follows the question, even symbol-only Japanese.

「OutputGuard？」 - a Latin keyword with a fullwidth 「？」 and no kana/kanji -
matched no evidence and got the English no-evidence reply, while 「あ」 got the
Japanese one. The language gate now counts Japanese punctuation/fullwidth
forms, so the Japanese user is answered in Japanese; kana/kanji questions
still are, and a plain English question stays English.
"""

from __future__ import annotations

from sidra_ai.evals.answer_language_matches_question import (
    evaluate_answer_language_matches_question,
)
from sidra_ai.models.base import GenerationRequest
from sidra_ai.models.echo import EchoModelAdapter, _is_japanese

_JA = "現時点では十分な根拠がありません"
_EN = "No indexed evidence matched this question"


def _no_evidence(question: str) -> str:
    req = GenerationRequest(system_prompt="", user_message=question, data_context="")
    return EchoModelAdapter().generate(req).text


def test_answer_language_eval_passes():
    result = evaluate_answer_language_matches_question()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_fullwidth_punct_question_answered_in_japanese():
    for q in ("OutputGuard？", "SIDRA！", "BM25。"):
        ans = _no_evidence(q)
        assert _JA in ans and _EN not in ans


def test_english_question_stays_english():
    ans = _no_evidence("retry policy?")
    assert _EN in ans and _JA not in ans


def test_is_japanese_helper():
    assert _is_japanese("あ")
    assert _is_japanese("OutputGuard？")
    assert _is_japanese("、")
    assert not _is_japanese("what is OutputGuard")
    assert not _is_japanese("retry policy?")
