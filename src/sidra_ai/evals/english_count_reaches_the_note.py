"""Does a count named in English actually reach the admission?

C-1954. Three generators cannot make the number someone asks for - one
mesh per request (C-1832), a fixed frame budget (C-1821's sibling in gifs),
four slides per outline (C-1821) - and each of them says so. C-1934 and
C-1935 taught those admissions English.

**One of the three was taught a phrasing the product never receives.**
Measured 2026-09-18 by running ``detect_creation_intent`` and
``models3d.requested_count`` side by side:

* 「make 3 models of an owl」 and 「make 3 meshes of an owl」 - the counter
  reads 3, and the intent parser reads ``unknown``. The request never
  reaches the lane.
* 「make 3 3d models of an owl」, 「make 3 3D models」 - the intent parser
  reads ``model3d``, and the counter read nothing, because 「3d」 sits
  between the number and the noun.

So the English branch matched exactly the requests that do not arrive, and
in the product it had never fired. The part was right and the product was
not, which is C-1640's family.

**What this counts.** Lanes whose English count is heard *through the
product's own path* - the intent parser, then the generator, then the text
a reader is given - out of every lane that has a count admission. Three,
measured end to end rather than by calling the parser directly, because
calling the parser directly is exactly how this went unnoticed for twenty
items.

The Japanese side is a GUARD (C-1939): the same request in Japanese must
still be admitted, or the count is zero.
"""

from __future__ import annotations

from dataclasses import dataclass

#: lane -> (English ask, Japanese ask). The asks are written the way the
#: product actually receives them; each is checked to reach its lane before
#: the note is looked for, so a phrasing that stops routing fails here rather
#: than passing quietly.
ASKS: dict[str, tuple[str, str]] = {
    "model3d": ("make 3 3d models of an owl", "ふくろうの 3D モデルを 3 つ作って"),
    "gif": ("make a 30 frame gif of an owl", "ふくろうの 30 フレームの GIF を作って"),
    "deck": ("make a 7 slide deck about owls", "ふくろうの 7 枚のスライドを作って"),
}


def _note_for(lane: str, request: str, *, in_japanese: bool) -> str:
    """The admission this lane's own builder produces for this request.

    Asked of the product rather than written out here: the sentence is the
    generator's, and a copy in the judge is a copy that goes stale (C-1848).
    """

    from sidra_ai.creation.decks import slide_count_note
    from sidra_ai.creation.gifs import length_note
    from sidra_ai.creation.models3d import count_note

    if lane == "model3d":
        return count_note(request, in_japanese=in_japanese)
    if lane == "gif":
        from sidra_ai.creation.gifs import FRAMES

        return length_note(request, FRAMES, in_japanese=in_japanese)
    return slide_count_note(request, 4, in_japanese=in_japanese)


@dataclass(frozen=True)
class EnglishCountResult:
    lanes_heard: int
    lanes_total: int
    japanese_held: bool = True
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _outcome_text(request: str, expected_kind: str) -> tuple[str, str]:
    """Everything a reader is given for this request, and why not."""

    from pathlib import Path

    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.router import build_default_router
    from sidra_ai.evals.scratch import scratch_dir

    intent = detect_creation_intent(request)
    if intent.kind.value != expected_kind:
        return "", (
            f"「{request}」 is read as {intent.kind.value}, not {expected_kind}"
        )
    directory = scratch_dir("sidra-english-count-")
    outcome = build_default_router(data_dir=str(directory)).route(request, intent)
    if not outcome.handled:
        return "", f"「{request}」 was not handled"
    text = outcome.summary
    path = Path(str(outcome.artifact_path or ""))
    # The page counts too: the admission belongs on the artifact that gets
    # forwarded, not only in the chat (C-1281, C-1832).
    if path.is_file() and path.suffix in (".html", ".md"):
        text += "\n" + path.read_text(encoding="utf-8", errors="replace")
    return text, ""


def evaluate_english_count_reaches_the_note() -> EnglishCountResult:
    failures: list[str] = []
    readings: list[str] = []
    heard = 0
    japanese_held = True

    for lane in sorted(ASKS):
        english_ask, japanese_ask = ASKS[lane]

        # The admission itself, not a digit. The first draft of this eval
        # looked for the number - and a page full of 「3D」, seeds and pixel
        # sizes contains "3" wherever you look, so it read 3/3 with the fix
        # reverted. A judge that cannot see the defect it was written for is
        # worse than none, and this is the second time in two days that
        # sabotage caught one of mine (C-1951's M2 was the first).
        note = _note_for(lane, english_ask, in_japanese=False).strip()
        text, why = _outcome_text(english_ask, lane)
        if why:
            failures.append(f"{lane}: {why}")
            readings.append(f"EN {lane} unreachable")
        elif not note:
            failures.append(
                f"{lane}: 「{english_ask}」 draws no admission at all - "
                "the count was not heard"
            )
            readings.append(f"EN {lane} silent")
        elif note not in text:
            failures.append(
                f"{lane}: the admission exists but never reaches the reader"
            )
            readings.append(f"EN {lane} unsaid")
        else:
            heard += 1
            readings.append(f"EN {lane} heard")

        note_ja = _note_for(lane, japanese_ask, in_japanese=True).strip()
        text_ja, why_ja = _outcome_text(japanese_ask, lane)
        if why_ja or not note_ja or note_ja not in text_ja:
            japanese_held = False
            failures.append(
                f"{lane} (ja): {why_ja or 'the admission no longer reaches the reader'}"
            )
            readings.append(f"JA {lane} SILENT")
        else:
            readings.append(f"JA {lane} heard")

    return EnglishCountResult(
        lanes_heard=heard if japanese_held else 0,
        lanes_total=len(ASKS),
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["ASKS", "EnglishCountResult", "evaluate_english_count_reaches_the_note"]
