"""Is the deck a request produces written in the language it was asked in?

C-1951. C-1935 put the deck's **summary** into the language of the request.
The page that summary points at was left alone, so 「make a slide deck about
owls」 answered in English about a file whose headings were 課題 / 解決 /
根拠となる数字 / 次の一歩, whose empty slots said 〔社長が埋める欄〕, whose
source lines said 出典なし and whose footer was a Japanese paragraph. The one
English word on it was the title the operator had typed.

That is the gap C-1939 named for the production set - "the reply was fixed,
the thing that gets opened was not" - still open one directory out, and this
loop has argued since C-1274 that the artifact matters more than the
sentence in the chat.

**What this counts.** Sides of the pair that come out right: the English
request's page in English, and the Japanese request's page unchanged. Both
are needed, and the Japanese side is a GUARD, so a gain on one side can
never pay for a loss on the other (C-1939 measured that failure).

Read off the artifact, not the generator's intentions (C-1640):

1. Not one Japanese character in the page written for an English request -
   **except inside the title**, which is the operator's own word and may be
   anything they typed.
2. ``<html lang>`` says what the page actually is. A page that always
   claimed Japanese would start lying the moment its headings turned
   English (WCAG 3.1.1).
3. It is still a deck: a title, one heading per section of the outline the
   product chose, and a footer.
4. The Japanese page is byte-identical to the one the Japanese request has
   always produced - checked by the page carrying its own headings, blank
   marker and footer words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

ENGLISH_ASK = "make a slide deck about owls"
JAPANESE_ASK = "ふくろうのスライドを作って"


@dataclass(frozen=True)
class DeckPageResult:
    sides_right: int
    sides_total: int = 2
    japanese_held: bool = True
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _without_title(html: str) -> str:
    """The page with the operator's own words taken out.

    The title appears in ``<title>`` and in the ``<h1>``; a Japanese subject
    typed into an English request belongs to the operator (C-1929), and a
    judge that counted it would be asking the product to translate someone's
    own noun.
    """

    without = re.sub(r"<title>.*?</title>", "", html, flags=re.S)
    return re.sub(r"<h1>.*?</h1>", "", without, flags=re.S)


def evaluate_deck_page_matches_the_language_asked() -> DeckPageResult:
    from sidra_ai.creation.decks import BLANK, OUTLINES, choose_outline, generate_deck

    failures: list[str] = []
    readings: list[str] = []
    right = 0
    japanese_held = True

    english = generate_deck(ENGLISH_ASK)
    body = _without_title(english.html)
    leftovers = [line for line in body.splitlines() if _JAPANESE.search(line)]
    sections = len(OUTLINES[choose_outline(ENGLISH_ASK)].sections)
    problems: list[str] = []
    if leftovers:
        problems.append(f"{len(leftovers)} lines are still Japanese")
    # On the <html> tag, not anywhere in the page: `marked_english` puts
    # `<span lang="en">` around an English title, so a search of the whole
    # document passes even when the page declares itself Japanese. Found by
    # sabotage M2 of this item - the first version of this check could not
    # see the very thing it was written for.
    declared = re.search(r'<html[^>]*\blang="([a-z-]+)"', english.html)
    if not declared or declared.group(1) != "en":
        problems.append(
            f"the page declares lang={declared.group(1) if declared else 'nothing'}"
        )
    if english.html.count("<h2>") != sections:
        problems.append(
            f"{english.html.count('<h2>')} headings against {sections} sections"
        )
    if "<footer>" not in english.html or "<h1>" not in english.html:
        problems.append("the page is no longer a deck")
    readings.append(f"EN ja-lines={len(leftovers)} h2={english.html.count('<h2>')}")
    if problems:
        failures.append("English: " + "; ".join(problems))
    else:
        right += 1

    japanese = generate_deck(JAPANESE_ASK)
    guard: list[str] = []
    declared_ja = re.search(r'<html[^>]*\blang="([a-z-]+)"', japanese.html)
    if not declared_ja or declared_ja.group(1) != "ja":
        guard.append("the Japanese page stopped declaring Japanese")
    if BLANK not in japanese.html:
        guard.append("the Japanese blank marker is gone")
    for section in OUTLINES[choose_outline(JAPANESE_ASK)].sections:
        if f"<h2>{section}</h2>" not in japanese.html:
            guard.append(f"「{section}」 is no longer a heading")
    if "SIDRA AI が生成" not in japanese.html:
        guard.append("the Japanese footer is gone")
    readings.append(
        "JA ja-lines="
        f"{len([l for l in japanese.html.splitlines() if _JAPANESE.search(l)])}"
    )
    if guard:
        japanese_held = False
        failures.append("Japanese: " + "; ".join(guard))
    else:
        right += 1

    return DeckPageResult(
        sides_right=right if japanese_held else 0,
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["DeckPageResult", "evaluate_deck_page_matches_the_language_asked"]
