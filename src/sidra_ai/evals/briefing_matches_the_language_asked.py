"""Is the start screen's briefing in the language the request was in?

C-1957. Three lines are drawn on the canvas before anything happens - what
to aim for, which keys, what is in the way (C-1033) - and they are the only
thing a player reads before pressing something. C-1956 put the page's frame
into the language of the request; the screen drawn on top of it stayed
Japanese.

**Read out of the page, not the table.** The lines reach the canvas through
one ``json.dumps`` into ``GBRIEF`` in the injected script, so this eval
pulls that array back out of the finished HTML. A judge that read
``BRIEFINGS_EN`` directly would pass while the injection still sent the
Japanese one - the shape C-1954 was caught by, where a part was right and
the product was not.

**What this counts.** Sides of the pair that come out right, with the
Japanese side as a GUARD rather than half the score (C-1939):

1. Not one Japanese character in the English page's three lines.
2. There are three of them, and they are the three the English table holds
   for that template - so "translating" a line by dropping it fails.
3. The number the product fills in is still filled in: racing's line
   carries the lap count, and a briefing that shipped the literal
   ``LAPS_TOKEN`` would be worse than a Japanese one.
4. The Japanese page still draws its own three lines.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")
_GBRIEF = re.compile(r"GBRIEF=(\[.*?\])", re.S)

#: A template whose briefing carries a number the product fills in, so the
#: filling is measured rather than assumed.
ENGLISH_ASK = "make a racing game about an owl"
JAPANESE_ASK = "ふくろうのレースゲームを作って"


@dataclass(frozen=True)
class BriefingResult:
    sides_right: int
    sides_total: int = 2
    japanese_held: bool = True
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _lines(html: str) -> list[str]:
    found = _GBRIEF.search(html)
    if not found:
        return []
    try:
        return list(json.loads(found.group(1)))
    except ValueError:
        return []


def evaluate_briefing_matches_the_language_asked() -> BriefingResult:
    from sidra_ai.creation.games import generate_game
    from sidra_ai.creation.startscreen import BRIEFINGS, BRIEFINGS_EN

    failures: list[str] = []
    readings: list[str] = []
    right = 0
    japanese_held = True

    english = _lines(generate_game(ENGLISH_ASK).html)
    wanted = len(BRIEFINGS_EN["racing"])
    problems: list[str] = []
    if not english:
        problems.append("the start screen has no briefing at all")
    else:
        leftovers = [line for line in english if _JAPANESE.search(line)]
        if leftovers:
            problems.append(f"{len(leftovers)} of its lines are still Japanese")
        if len(english) != wanted:
            problems.append(f"{len(english)} lines, wanted {wanted}")
        if any("LAPS_TOKEN" in line for line in english):
            problems.append("the lap count was never filled in")
        if not any(re.search(r"\d", line) for line in english):
            problems.append("no number reached the line that carries one")
    readings.append(f"EN lines={len(english)}")
    if problems:
        failures.append("English: " + "; ".join(problems))
    else:
        right += 1

    japanese = _lines(generate_game(JAPANESE_ASK).html)
    guard: list[str] = []
    if len(japanese) != len(BRIEFINGS["racing"]):
        guard.append(f"{len(japanese)} lines, wanted {len(BRIEFINGS['racing'])}")
    elif not all(_JAPANESE.search(line) for line in japanese):
        guard.append("a line of the Japanese briefing is no longer Japanese")
    if any("LAPS_TOKEN" in line for line in japanese):
        guard.append("the lap count was never filled in")
    readings.append(f"JA lines={len(japanese)}")
    if guard:
        japanese_held = False
        failures.append("Japanese: " + "; ".join(guard))
    else:
        right += 1

    return BriefingResult(
        sides_right=right if japanese_held else 0,
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["BriefingResult", "evaluate_briefing_matches_the_language_asked"]
