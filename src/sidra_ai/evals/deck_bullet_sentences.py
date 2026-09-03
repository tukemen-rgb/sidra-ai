"""Do deck bullets end at a sentence instead of a 120-character cliff?

C-1217: with the real corpus, the one filled slide of a requested revenue
deck carried three bullets and all three ended mid-word -
「…（components/UploadForm.ts」「…） 注意」「…revenue-model.md の」.
``_bullets_for`` re-cut already-trimmed facts at a hard 120 characters,
the second cut site of the exact failure C-1213 fixed at the first one.
And ``whole_sentences`` itself counted the dot inside 「revenue-model.md」
as a sentence end, so trimming there would end a bullet mid-filename.

The checks build a deck from crafted facts through the public generator;
the live proof (regenerated deck over the real corpus) ran at fix time and
is recorded in the loop log.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.decks import BLANK, generate_deck
from sidra_ai.creation.evidence import Fact

_SRC = "tukemen-rgb/site docs/policy.md"

#: 課題 (cue 「問題」): the 120-character window lands mid-word, and the
#: last terminator sits far enough in that trimming keeps the substance.
_FACT_MIDCUT = Fact(
    text=(
        "問題は投稿画面の同意文書が二重になっていることだと運用メモの決定記録も"
        "レビューの控えもどちらも同じ言い回しで繰り返し述べている。"
        "この段落はまだ続いていて百二十文字の窓のちょうど途中で切れる長さになるように"
        "書き足された文がこの先も延々と続いていて句点の無いまま窓の外まで"
        "余りの文字が薄く引き伸ばされて到達する"
    ),
    source=_SRC,
)

#: 課題 (cue "problem"): an ASCII sentence end past the minimum keeps
#: working as a cut point.
_FACT_ASCII = Fact(
    text=(
        "This problem statement about the deck generator ends properly. "
        "And the trailing continuation is long enough that the window must "
        "land somewhere inside this second sentence, whose own full stop "
        "sits well past the display cap."
    ),
    source=_SRC,
)

#: 解決 (cue 「解決」): no terminator at all - must pass through whole.
_FACT_FRAGMENT = Fact(
    text="解決の合言葉: 正直第一 数字は実測 出典を添える 推測で埋めない 断片も残す",
    source=_SRC,
)

#: 解決 (cue 「対応」): the only terminator sits near the head; trimming
#: there would throw away the content to polish the punctuation.
_FACT_EARLY_END = Fact(
    text="対応の合言葉。正直第一 数字は実測 出典を添える 推測で埋めない 断片も残すことが大事",
    source=_SRC,
)

#: 次の一歩 (cue 「次」): terminator-free except the dots inside filenames,
#: which are spelling, not sentence ends.
_FACT_FILENAME = Fact(
    text=(
        "次はこの参照の向きをそろえる作業が残っていて対象は収益方針の本文と"
        "その脇に置かれた revenue-model.md の続きにある一覧表"
    ),
    source=_SRC,
)


@dataclass(frozen=True)
class DeckBulletSentencesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_bullet_sentences() -> DeckBulletSentencesResult:
    deck = generate_deck(
        "収益方針についてスライドを作って",
        facts=[_FACT_MIDCUT, _FACT_ASCII, _FACT_FRAGMENT, _FACT_EARLY_END, _FACT_FILENAME],
    )
    by_title = {slide.title: slide for slide in deck.slides}
    problem = by_title["課題"].bullets
    solution = by_title["解決"].bullets
    next_step = by_title["次の一歩"].bullets

    checks = 0
    failures: list[str] = []

    if problem and problem[0].endswith("。"):
        checks += 1
    else:
        failures.append("mid-cut bullet does not end at a sentence")

    if all(len(bullet) <= 120 for slide in deck.slides for bullet in slide.bullets):
        checks += 1
    else:
        failures.append("a bullet exceeds the 120-character display cap")

    if len(problem) > 1 and problem[1].endswith("properly."):
        checks += 1
    else:
        failures.append("ASCII sentence end no longer works as a cut point")

    if solution and solution[0] == _FACT_FRAGMENT.text:
        checks += 1
    else:
        failures.append("terminator-free fragment was not passed through whole")

    if len(solution) > 1 and "断片も残す" in solution[1]:
        checks += 1
    else:
        failures.append("early-terminator bullet lost its content to polish")

    if next_step and "revenue-model.md" in next_step[0] and not next_step[0].endswith("revenue-model."):
        checks += 1
    else:
        failures.append("a filename dot was treated as a sentence end")

    numeric = by_title["根拠となる数字"].bullets
    if numeric == (BLANK,):
        checks += 1
    else:
        failures.append("a section with no matching evidence was filled anyway")

    return DeckBulletSentencesResult(
        passed=not failures, checks_passed=checks, checks_total=7,
        failures=tuple(failures),
    )
