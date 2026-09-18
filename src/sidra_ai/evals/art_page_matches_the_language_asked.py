"""Is the art page written in the language it was asked in?

C-1952, and the second of the pages C-1951 named. C-1932 put the art
generator's **summary** into the language of the request; the HTML it points
at stayed Japanese, so 「draw a picture of an owl」 answered in English about
a page whose canvas fallback read 「{title}——流れる線がゆっくり動く抽象画」
and whose three honesty notes - the default pattern, the ignored colour, the
undrawn subject - were Japanese paragraphs. The operator's own title was the
only English on it.

The notes are the part that matters most. They exist because the page must
admit what it did not do (C-1284, C-1786, C-1806); an admission a reader
cannot read is not one.

**What this counts.** Sides of the pair that come out right, with the
Japanese side as a GUARD rather than half the score (C-1939). Read off the
page (C-1640):

1. Not one Japanese character in the page written for an English request,
   **outside the title**, which is the operator's own word (C-1929).
2. ``<html lang>`` says what the page is - the rule
   ``english_title_is_marked_english`` was generalised to in C-1951.
3. The page still carries what it must: the canvas fallback sentence and
   every note the request earns.
4. The Japanese page still has its own words.

Written as its own metric rather than folded into the deck's (C-1951) on
purpose: widening that one from two sides to four would read as 2 -> 4 on
the board, and the deck side would not have improved at all. The two merge
into one "artifact pages in the language asked" number when the remaining
pages - game, model3d, gif - are done, and not before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: Asks that earn all three notes at once: no pattern named, a colour named,
#: and a subject the abstract art will not draw.
ENGLISH_ASK = "draw a picture of a blue owl"
JAPANESE_ASK = "青いふくろうの絵を描いて"


@dataclass(frozen=True)
class ArtPageResult:
    sides_right: int
    sides_total: int = 2
    japanese_held: bool = True
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def evaluate_art_page_matches_the_language_asked() -> ArtPageResult:
    from sidra_ai.creation.art import generate_art

    failures: list[str] = []
    readings: list[str] = []
    right = 0
    japanese_held = True

    english = generate_art(ENGLISH_ASK)
    body = english.html.replace(english.title, " ")
    leftovers = [line for line in body.splitlines() if _JAPANESE.search(line)]
    declared = re.search(r'<html[^>]*\blang="([a-z-]+)"', english.html)
    notes = english.html.count('<p class="note">')
    problems: list[str] = []
    if leftovers:
        problems.append(f"{len(leftovers)} lines are still Japanese")
    if not declared or declared.group(1) != "en":
        problems.append(
            f"the page declares lang={declared.group(1) if declared else 'nothing'}"
        )
    if notes != 3:
        # The ask earns all three: no pattern, a colour, a subject. A page
        # that lost one would be "in English" by rule 1 while saying less
        # than the Japanese one does - translation by deletion, the escape
        # C-1941's third rule closes for the production set.
        problems.append(f"{notes} notes, wanted the 3 this request earns")
    if "<canvas" not in english.html or "abstract picture" not in english.html:
        problems.append("the canvas fallback sentence is gone")
    readings.append(f"EN ja-lines={len(leftovers)} notes={notes}")
    if problems:
        failures.append("English: " + "; ".join(problems))
    else:
        right += 1

    japanese = generate_art(JAPANESE_ASK)
    guard: list[str] = []
    declared_ja = re.search(r'<html[^>]*\blang="([a-z-]+)"', japanese.html)
    if not declared_ja or declared_ja.group(1) != "ja":
        guard.append("the Japanese page stopped declaring Japanese")
    if japanese.html.count('<p class="note">') != 3:
        guard.append("the Japanese page lost a note")
    for phrase in ("抽象画", "既定の「フロー」", "題材は描いていません"):
        if phrase not in japanese.html:
            guard.append(f"「{phrase}」 is gone from the Japanese page")
    readings.append(
        "JA ja-lines="
        f"{len([l for l in japanese.html.splitlines() if _JAPANESE.search(l)])}"
    )
    if guard:
        japanese_held = False
        failures.append("Japanese: " + "; ".join(guard))
    else:
        right += 1

    return ArtPageResult(
        sides_right=right if japanese_held else 0,
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["ArtPageResult", "evaluate_art_page_matches_the_language_asked"]
