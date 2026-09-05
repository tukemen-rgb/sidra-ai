"""A question with no language signal is answered in Japanese, not English.

C-1248: the no-evidence reply (and the framing preamble) chose English whenever
``_is_japanese`` was false. A query written only in digits, symbols, emoji, or
nothing at all carries no language, yet it fell to the English branch - so a
Japanese reader who typed 「123456」 or 「😀」 got 「No indexed evidence matched
this question. Run POST /v1/github/analyze…」, English with an internal API
term. This product's readers are Japanese, so a question that is not in a Latin
script defaults to Japanese; a genuine English/romaji question still gets
English (SYSTEM_PROMPT rule 6).

The checks drive the echo model with no data block (the no-evidence path) over
questions with no language signal, a real Japanese question, and a real English
question, and confirm the language of the reply.
"""

from __future__ import annotations

from dataclasses import dataclass

_EN_MARKER = "No indexed evidence matched this question"
_JA_MARKER = "現時点では十分な根拠がありません"

#: Questions with no Latin letters and no CJK - no language to match.
_NO_LANGUAGE = ("123456", "😀😀", "?!?!", "...", "   ")


@dataclass(frozen=True)
class AnswerLanguageDefaultsJapaneseResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _no_evidence_answer(message: str) -> str:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    # No data block -> the no-evidence branch, where the language is chosen.
    return EchoModelAdapter().generate(
        GenerationRequest(system_prompt="", user_message=message, data_context="")
    ).text


def evaluate_answer_language_defaults_japanese() -> AnswerLanguageDefaultsJapaneseResult:
    checks = 0
    total = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks, total
        total += 1
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # No-language questions default to Japanese, and never leak the English
    # 「Run POST /v1/github/analyze」 line.
    for q in _NO_LANGUAGE:
        ans = _no_evidence_answer(q)
        add(
            _JA_MARKER in ans and _EN_MARKER not in ans,
            f"no-language {q!r} answered in English",
        )

    # A real Japanese question stays Japanese.
    add(_JA_MARKER in _no_evidence_answer("存在しない社名の決算は"),
        "a Japanese question was not answered in Japanese")

    # A genuine English/romaji question still gets English - not over-corrected.
    en = _no_evidence_answer("what is the quarterly revenue")
    add(_EN_MARKER in en and _JA_MARKER not in en,
        "an English question was not answered in English")

    return AnswerLanguageDefaultsJapaneseResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "AnswerLanguageDefaultsJapaneseResult",
    "evaluate_answer_language_defaults_japanese",
]
