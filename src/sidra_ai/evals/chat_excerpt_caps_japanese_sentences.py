"""Does the chat excerpt cap Japanese sentences the way it caps English?

C-1518. The echo ``_lead`` limited each citation's excerpt to
``max_sentences_per_block`` (2) informative sentences, but it split sentences
on ``(?<=[.。!?！？])\\s+`` - whitespace required after the terminator. Japanese
prose puts no space after 「。」, so a whole 「…です。…です。…です。」 block counted
as one sentence, the 2-sentence budget never fired, and the answer dumped the
entire block (to 400 chars) in the product's main language. English (spaces
after periods) was correctly capped.

``_lead`` now finds sentence boundaries by position: a CJK terminator ends a
sentence on its own, an ASCII terminator only before whitespace (so 「3.5」 and
「e.g.」 stay intact). Japanese is now capped at two sentences too, and slicing
the original text keeps its spacing.
"""

from __future__ import annotations

from dataclasses import dataclass

_JP_FOUR = (
    "第一文は十分に長い説明の文章です。第二文も十分に長い説明の文章です。"
    "第三文は現れてはいけない内容です。第四文も現れてはいけません。"
)
_JP_BANG = (
    "最初の文は十分に長い驚きの説明です！次の文も十分に長い説明の文章です！"
    "三番目の文は出てはいけません！"
)
_JP_DECIMAL = (
    "速度は3.5倍に向上した実測の結果です。次の目標は10倍の高速化になります。"
    "三つ目の文は出てはいけません。"
)
_JP_SINGLE = "これは終端記号のない十分に長い一つの文だけの内容です"
_EN_THREE = (
    "First sentence long enough to count. "
    "Second sentence also long enough to count. "
    "Third must not appear in the lead."
)


@dataclass(frozen=True)
class ChatExcerptCapResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _data_block(label: str, source: str, content: str) -> str:
    return (
        f"<<<SIDRA_DATA_BLOCK {label}>>>\n"
        f"source: {source}\n"
        "trust: retrieved-data\n"
        f"content:\n{content}\n"
        f"<<<END_SIDRA_DATA_BLOCK {label}>>>"
    )


def evaluate_chat_excerpt_caps_japanese_sentences() -> ChatExcerptCapResult:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    model = EchoModelAdapter()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    jp = model._lead(_JP_FOUR)
    add("第一文" in jp, "JP excerpt lost the first sentence")
    add("第二文" in jp, "JP excerpt lost the second sentence")
    add("第三文" not in jp, "JP excerpt overran into the third sentence")
    add("第四文" not in jp, "JP excerpt overran into the fourth sentence")

    bang = model._lead(_JP_BANG)
    add("最初の文" in bang and "次の文" in bang, "JP ！ excerpt lost its first two sentences")
    add("三番目" not in bang, "JP ！ excerpt overran the sentence budget")

    dec = model._lead(_JP_DECIMAL)
    add("3.5倍" in dec, "an ASCII decimal was split as a sentence boundary")
    add("三つ目" not in dec, "JP decimal excerpt overran the sentence budget")

    single = model._lead(_JP_SINGLE)
    add(single == _JP_SINGLE, "a single terminatorless JP sentence was altered")

    # English regression guard, end to end through generate().
    answer = model.generate(
        GenerationRequest(
            system_prompt="",
            user_message="tell me about it",
            data_context=_data_block("S1", "repo@aaaaaaa:docs/plain.md", _EN_THREE),
        )
    ).text
    add(
        "Second sentence also long enough to count." in answer
        and "Third must not appear" not in answer,
        "English excerpt cap regressed",
    )

    total = 10
    return ChatExcerptCapResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ChatExcerptCapResult", "evaluate_chat_excerpt_caps_japanese_sentences"]
