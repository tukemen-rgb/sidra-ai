"""Does the answer's language follow the question's, even for symbol-only JP?

C-1231: 「OutputGuard？」 - a Japanese user asking about a product feature
with a Latin keyword and a fullwidth 「？」, matching no evidence - got the
*English* no-evidence reply, while 「あ」 got the Japanese one. The language
gate counted only kana and kanji, so a question written with Japanese
punctuation but no kana/kanji (fullwidth 「？！」, ideographic 「、。」) was
read as English. That breaks SYSTEM_PROMPT rule 6 (a Japanese question is
answered in Japanese; the 2026-08-27 incident, C-1202).

The checks drive the echo backend directly - no retrieval, so the
no-evidence branch fires - and confirm: a Japanese-punctuation-only question
gets the Japanese abstention, a kana question still does, and a plain
English question still gets the English one. A tiny answered-path check
confirms the same gate routes the preamble.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnswerLanguageResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


_JA_MARKER = "現時点では十分な根拠がありません"
_EN_MARKER = "No indexed evidence matched this question"
_JA_PREAMBLE = "索引済みリポジトリの DATA から回答します"
_EN_PREAMBLE = "Answering from indexed repository DATA"


def _no_evidence_answer(question: str) -> str:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    # Empty data_context => no blocks => the no-evidence branch.
    req = GenerationRequest(
        system_prompt="",
        user_message=question,
        data_context="",
    )
    return EchoModelAdapter().generate(req).text


def _answered_preamble(question: str) -> str:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    block = (
        "<<<SIDRA_DATA_BLOCK S1>>>\n"
        "source: repo@abc:docs/x.md\n"
        "trust: DATA\n"
        "content:\n"
        "OutputGuard は高エントロピー文字列を伏せます。\n"
        "<<<END_SIDRA_DATA_BLOCK S1>>>"
    )
    req = GenerationRequest(
        system_prompt="",
        user_message=question,
        data_context=block,
    )
    return EchoModelAdapter().generate(req).text


def evaluate_answer_language_matches_question() -> AnswerLanguageResult:
    checks = 0
    failures: list[str] = []

    # 1-4: symbol/latin questions a Japanese user types (fullwidth ？！,
    # ideographic 、。) must get the Japanese abstention, not the English one.
    japanese_by_punct = ("OutputGuard？", "SIDRA！", "zip 上限、", "BM25。")
    for q in japanese_by_punct:
        ans = _no_evidence_answer(q)
        if _JA_MARKER in ans and _EN_MARKER not in ans:
            checks += 1
        else:
            failures.append(f"{q!r}: no-evidence reply not in Japanese")

    # 5-6: kana/kanji questions still route to Japanese (regression guard).
    for q in ("あ", "リトライは"):
        ans = _no_evidence_answer(q)
        if _JA_MARKER in ans and _EN_MARKER not in ans:
            checks += 1
        else:
            failures.append(f"{q!r}: kana/kanji question lost Japanese routing")

    # 7-8: a genuinely English question still gets the English reply - the
    # fix must not flip every question to Japanese.
    for q in ("what is OutputGuard", "retry policy?"):
        ans = _no_evidence_answer(q)
        if _EN_MARKER in ans and _JA_MARKER not in ans:
            checks += 1
        else:
            failures.append(f"{q!r}: English question lost English routing")

    # 9: the same gate drives the answered-path preamble - a Japanese-punct
    # question that *does* match evidence opens in Japanese.
    if _JA_PREAMBLE in _answered_preamble("OutputGuard？"):
        checks += 1
    else:
        failures.append("answered preamble not Japanese for 'OutputGuard？'")

    # 10: and an English question keeps the English preamble.
    if _EN_PREAMBLE in _answered_preamble("what is OutputGuard"):
        checks += 1
    else:
        failures.append("answered preamble not English for English question")

    return AnswerLanguageResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=10,
        failures=tuple(failures),
    )
