"""C-1248: a question with no language signal is answered in Japanese.

The no-evidence reply (and the framing preamble) chose English whenever
``_is_japanese`` was false, so a query of only digits, symbols, emoji, or
nothing fell to English - 「Run POST /v1/github/analyze」 to a Japanese reader.
A non-Latin-script question now defaults to Japanese; a real English question
still gets English.
"""

from __future__ import annotations

from sidra_ai.models.base import GenerationRequest
from sidra_ai.models.echo import EchoModelAdapter, _reply_in_japanese
from sidra_ai.evals.answer_language_defaults_japanese import (
    evaluate_answer_language_defaults_japanese,
)

_JA = "現時点では十分な根拠がありません"
_EN = "No indexed evidence matched this question"


def _no_evidence(message: str) -> str:
    return EchoModelAdapter().generate(
        GenerationRequest(system_prompt="", user_message=message, data_context="")
    ).text


def test_eval_passes():
    result = evaluate_answer_language_defaults_japanese()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_no_language_questions_answer_japanese():
    for q in ("123456", "😀😀", "?!?!", "...", "   ", ""):
        ans = _no_evidence(q)
        assert _JA in ans and _EN not in ans, (q, ans[:40])


def test_english_question_stays_english():
    ans = _no_evidence("what is the quarterly revenue")
    assert _EN in ans and _JA not in ans


def test_japanese_question_stays_japanese():
    assert _JA in _no_evidence("存在しない社名の決算は")


def test_reply_in_japanese_helper():
    assert _reply_in_japanese("") is True
    assert _reply_in_japanese("123") is True
    assert _reply_in_japanese("😀") is True
    assert _reply_in_japanese("？！") is True  # fullwidth -> Japanese
    assert _reply_in_japanese("GAMEYARD") is False  # Latin -> English
    assert _reply_in_japanese("GAMEYARD の売上") is True  # mixed -> Japanese
