"""Is a number written as a word heard - in either language?

C-1955. Three generators cannot make the number asked for and each says so
(C-1821, C-1823, C-1832); C-1934/C-1935 taught those admissions English and
C-1954 made the English count actually reach them. All of that was about
digits.

**Measured 2026-09-18: a number written as a word was heard by neither
language.** 「三つの 3D モデルを作って」, 「3D モデルを三つ作って」,
「五枚のスライドを作って」 and 「三十フレームの GIF を作って」 all returned
no count, and so did 「make three 3d models」, 「make a five slide deck」 and
「make a thirty frame gif」. Every one of them reaches its lane. So the asker
gets a different number than they wrote and is told nothing about it - in
the product's primary language as much as in English.

C-1954's entry said "the siblings do not read spelled numbers either, so
this is not an English gap". That was true and it was not a reason to stop:
a silence shared by both languages is still a silence.

**What this counts.** Lane-and-language pairs whose spelled count is heard
through the product's own path - three lanes, two languages, six. Read end
to end (intent parser, generator, the text a reader is given), because
calling a parser directly is how C-1954's defect hid for twenty items.

The admission itself is compared, never a digit: a page carrying 「3D」,
seeds and pixel sizes contains "3" wherever you look, and that is exactly
how C-1954's first judge read full marks over a defect it was written for.
"""

from __future__ import annotations

from dataclasses import dataclass

#: (lane, language) -> the ask written as a word, and the number it names.
#:
#: The number is checked, not just the presence of an admission. Sabotage R3
#: of this item deleted 「三十」 from the table and this eval still read 6/6:
#: 「三十フレーム」 fell back to 「三」+「十」 and became 310, so a note still
#: fired - about the wrong number. That is the sixth time in this loop that
#: a table's breaking row could be removed in silence (C-1896 D4, C-1920 D3,
#: C-1928 D3, C-1937 D5, C-1945 G2), and the answer is the same one: measure
#: what the row is for, not that something happened.
ASKS: dict[tuple[str, str], tuple[str, int]] = {
    ("model3d", "en"): ("make three 3d models of an owl", 3),
    ("model3d", "ja"): ("ふくろうの 3D モデルを三つ作って", 3),
    ("gif", "en"): ("make a thirty frame gif of an owl", 30),
    ("gif", "ja"): ("ふくろうの三十フレームの GIF を作って", 30),
    ("deck", "en"): ("make a five slide deck about owls", 5),
    ("deck", "ja"): ("ふくろうの五枚のスライドを作って", 5),
}


@dataclass(frozen=True)
class SpelledCountResult:
    pairs_heard: int
    pairs_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def evaluate_spelled_count_reaches_the_note() -> SpelledCountResult:
    from sidra_ai.evals.english_count_reaches_the_note import _note_for, _outcome_text

    failures: list[str] = []
    readings: list[str] = []
    heard = 0

    for (lane, language), (ask, asked_for) in sorted(ASKS.items()):
        in_japanese = language == "ja"
        note = _note_for(lane, ask, in_japanese=in_japanese).strip()
        text, why = _outcome_text(ask, lane)
        if why:
            failures.append(f"{lane}/{language}: {why}")
            readings.append(f"{language.upper()} {lane} unreachable")
        elif not note:
            failures.append(
                f"{lane}/{language}: 「{ask}」 draws no admission - the "
                "spelled count was not heard"
            )
            readings.append(f"{language.upper()} {lane} silent")
        elif str(asked_for) not in note:
            failures.append(
                f"{lane}/{language}: the admission names a different number "
                f"than the {asked_for} that was asked for - 「{note[:40]}…」"
            )
            readings.append(f"{language.upper()} {lane} wrong-number")
        elif note not in text:
            failures.append(
                f"{lane}/{language}: the admission exists but never reaches "
                "the reader"
            )
            readings.append(f"{language.upper()} {lane} unsaid")
        else:
            heard += 1
            readings.append(f"{language.upper()} {lane} heard")

    return SpelledCountResult(
        pairs_heard=heard,
        pairs_total=len(ASKS),
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["ASKS", "SpelledCountResult", "evaluate_spelled_count_reaches_the_note"]
