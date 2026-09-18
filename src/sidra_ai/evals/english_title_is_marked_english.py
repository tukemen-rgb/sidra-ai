"""Does a Japanese page tell the screen reader which words are English?

Every SIDRA page declares its language on `<html>`, which satisfies SC 3.1.1
Language of Page (Level A). SC 3.1.2 Language of Parts (Level AA) asks for
more: the language of each passage or phrase has to be programmatically
determinable, so a speech synthesizer can reach for the right accent and
pronunciation (§37, and the standard's own stated reason).

That became a live gap rather than a theoretical one. C-1913 and C-1916
made an English request produce a genuinely English title - 「owl」,
「octopus」 - and C-1907 put the title into the canvas's fallback content
while C-1908 put page text into a live region, which is exactly where a
screen reader picks it up. So a Japanese page was handing a Japanese voice
an unmarked English word, three or four times over.

What this reads is the **finished page**, not the helper: all four
surfaces that build one - games, art, decks and the 3D preview - are
driven and their HTML parsed (C-1640). Documents produce markdown and
gifs produce image bytes, so neither has a `lang` to get wrong; that was
measured rather than assumed (C-1920).

Four things, because each of the plausible wrong fixes passes the others:

  (a) every DISPLAYED occurrence of an English title carries `lang="en"`.
      `<title>` is excluded on purpose - it is a text-only element and
      cannot hold a mark, which §37 records as the specification's limit
      rather than a defect to paper over.
  (b) a Japanese request's page carries NO `lang="en"` anywhere. A marker
      that marks everything tells the reader nothing, and would make the
      rest of the page read in the wrong voice.
  (c) nothing inside a `lang="en"` span is Japanese. The honesty note is
      one Japanese sentence quoting the operator's word, so marking the
      whole line is the obvious wrong fix - and it satisfies (a).
  (d) the page declares a language, and the declaration is true: it may
      say English only if its own text - everything but the operator's own
      title - really is English. (a) is trivially satisfiable by flipping
      the document to English and breaking 3.1.1 instead, and that cheat is
      what this catches. It used to be written as "still `lang="ja"`",
      which was the same thing only while every page was Japanese; C-1951
      made the deck page follow the request, and the narrower wording would
      have called a correctly English page a regression.
  (e) and where a surface lets a model overlay the wording afterwards
      (`with_copy`), the heading still follows the new title. Marking the
      heading makes that overlay's anchor fragile - it has to be built in
      the marked form or it matches nothing and the page silently keeps the
      old wording while `<title>` moves on. That is the regression
      `test_game_copy_overlay` caught for C-1907; the deck had no such test
      because its own only uses a Japanese title, which is never marked, so
      sabotage D3 of C-1920 went green until this check existed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: (request, the title the page ends up with, how many DISPLAYED places
#: carry it). Counted from the running page, and asserted rather than
#: derived, so a change that quietly drops one of the places is a failure
#: instead of a smaller number nobody reads.
ENGLISH_CASES: tuple[tuple[str, str, str, int], ...] = (
    ("game", "make a game about an octopus", "octopus", 3),
    ("game", "make a racing game with an alien", "alien", 2),
    ("art", "make art of an owl", "owl", 2),
    ("art", "make art of abstract shapes", "abstract shapes", 2),
    # C-1920: the other two surfaces that build an HTML page. The deck shows
    # its title once (the cover heading); the 3D preview shows it twice, and
    # the second is the canvas's fallback content - the only string a reader
    # who cannot see the spinning solid is handed at all (§36).
    ("deck", "make a deck about an owl", "owl", 1),
    ("deck", "make a deck about abstract shapes", "abstract shapes", 1),
    ("model3d", "make a model of an owl", "owl", 2),
    ("model3d", "make a model of an octopus", "octopus", 2),
)

#: The same two surfaces asked in Japanese. Nothing here may be marked.
JAPANESE_CASES: tuple[tuple[str, str], ...] = (
    ("game", "レースゲームを作って"),
    ("game", "釣りゲームを作って"),
    ("art", "海のアートを作って"),
    ("art", "螺旋のアートを作って"),
    ("deck", "事業計画のスライドを作って"),
    ("model3d", "魚の3Dモデルを作って"),
)

_JAPANESE_SCRIPT = re.compile(r"[぀-ゟ゠-ヿ一-鿿々ー]")
_SPAN_EN = re.compile(r'<span lang="en">(.*?)</span>', re.S)
_SCRIPTISH = re.compile(r"<script.*?</script>|<style.*?</style>", re.S)
_TITLE_EL = re.compile(r"<title>.*?</title>", re.S)
_H1 = re.compile(r"<h1>(.*?)</h1>", re.S)
_HTML_TAG = re.compile(r"<html[^>]*>")


@dataclass(frozen=True)
class MarkedEnglishResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _render(surface: str, request: str) -> str:
    """The finished page for one surface, however that surface hands it over.

    The four do not agree on the field: games and art carry `.html`, decks
    carry `.html` too, and the 3D model carries `.preview_html` beside the
    .obj/.mtl it exists to produce. Documents (markdown) and gifs (image
    bytes) build no HTML page at all, so they are not here - measured, not
    assumed (C-1920).
    """

    from sidra_ai.creation.art import generate_art
    from sidra_ai.creation.decks import generate_deck
    from sidra_ai.creation.games import generate_game
    from sidra_ai.creation.models3d import generate_model3d

    if surface == "game":
        return generate_game(request).html
    if surface == "art":
        return generate_art(request).html
    if surface == "deck":
        return generate_deck(request).html
    if surface == "model3d":
        return generate_model3d(request).preview_html
    raise ValueError(f"no renderer for surface {surface!r}")


def _displayed(html: str) -> str:
    """The page with its scripts, styles and text-only <title> taken out."""

    return _TITLE_EL.sub("", _SCRIPTISH.sub("", html))


#: Japanese script, for deciding whether a page that claims another language
#: is telling the truth about its own text.
_JAPANESE_TEXT = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")


def _without_title(shown: str, title: str) -> str:
    """The displayed text minus the operator's own words.

    A title is whatever the operator typed and may be in any language
    (C-1929); it is the one thing on the page this product does not choose.
    """

    return shown.replace(title, " ")


def evaluate_english_title_is_marked_english() -> MarkedEnglishResult:
    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    # The table first: a sheet that only asks English requests cannot catch a
    # marker that marks everything, and one that only asks Japanese cannot
    # catch a marker that marks nothing. Both surfaces need both.
    for surface in ("game", "art", "deck", "model3d"):
        has_en = any(s == surface for s, _r, _t, _n in ENGLISH_CASES)
        has_ja = any(s == surface for s, _r in JAPANESE_CASES)
        if has_en and has_ja:
            checks += 1
        else:
            failures.append(
                f"{surface}: the table needs both an English and a Japanese "
                f"request (english={has_en}, japanese={has_ja})"
            )

    for surface, request, title, places in ENGLISH_CASES:
        html = _render(surface, request)
        shown = _displayed(html)

        # (d) the document declares a language, and the declaration is true.
        #
        # This check used to say "and it is still ja", against the cheat of
        # satisfying (a) by flipping the document to English while leaving
        # Japanese text on it - 3.1.1 broken instead of 3.1.2 served. The
        # cheat is still caught, but the rule is now the one that was meant:
        # a page may say English only if its own text (everything but the
        # operator's title) really is. C-1951 made that reachable - the deck
        # page follows the language of the request now - and this check
        # would have called a correctly English page a regression.
        tag = _HTML_TAG.search(html)
        declared = re.search(r'\blang="([a-z-]+)"', tag.group(0)) if tag else None
        page_language = declared.group(1) if declared else ""
        if not page_language:
            failures.append(
                f"{surface}「{request}」: the document declares no language "
                f"({tag.group(0) if tag else 'no <html> tag'})"
            )
        elif page_language == "ja":
            checks += 1
        elif _JAPANESE_TEXT.search(_without_title(shown, title)):
            failures.append(
                f"{surface}「{request}」: the document says lang=\"{page_language}\" "
                "while its own text is still Japanese"
            )
        else:
            checks += 1

        marked = _SPAN_EN.findall(shown)
        mine = [m for m in marked if m == title]

        # (a) the title is marked everywhere it is displayed
        if len(mine) < places:
            failures.append(
                f"{surface}「{request}」: 「{title}」 is marked in {len(mine)} "
                f"displayed place(s), wanted {places}"
            )
        else:
            checks += 1

        # ...and nowhere is it displayed unmarked. Blank out the marked spans
        # first; whatever is left is an occurrence with no mark on it.
        bare = _SPAN_EN.sub("", shown)
        if title in bare:
            failures.append(
                f"{surface}「{request}」: 「{title}」 is still displayed "
                "somewhere without a lang mark"
            )
        else:
            checks += 1

        # (c) and no Japanese was dragged inside a mark
        swallowed = [m for m in marked if _JAPANESE_SCRIPT.search(m)]
        if swallowed:
            failures.append(
                f"{surface}「{request}」: the mark swallowed Japanese text - "
                f"「{swallowed[0][:40]}」"
            )
        else:
            checks += 1

        readings.append(f"{surface}「{request}」→ 「{title}」×{len(mine)}")

    # (e) the overlay path, for the surfaces that have one
    for surface, was, now in (
        ("game", "make a game about an octopus", "giant squid"),
        ("deck", "make a deck about an owl", "barn owl"),
    ):
        from sidra_ai.creation.decks import generate_deck
        from sidra_ai.creation.games import generate_game

        built = (generate_game if surface == "game" else generate_deck)(was)
        after = built.with_copy(title=now)
        head = _H1.search(after.html)
        # The HEADING, not the whole page. A game's honesty note quotes the
        # subject the operator actually asked for and explains why it was not
        # depicted - rewriting that to a model's later title would make the
        # note lie, so `with_copy` leaves it alone by design (C-1431). This
        # check went red on exactly that before it was narrowed, which is the
        # judge being wrong rather than the page.
        inside = head.group(1) if head else ""
        if inside != f'<span lang="en">{now}</span>':
            failures.append(
                f"{surface}: after with_copy(「{now}」) the heading reads "
                f"「{inside}」 - the overlay's anchor no longer matches the "
                "marked heading, so the page keeps the old wording"
            )
        else:
            checks += 1
            readings.append(f"{surface} with_copy →「{now}」")

    # (b) a Japanese page carries no mark at all
    for surface, request in JAPANESE_CASES:
        html = _render(surface, request)
        marked = _SPAN_EN.findall(_displayed(html))
        if marked:
            failures.append(
                f"{surface}「{request}」: a Japanese page carries "
                f"{len(marked)} lang=\"en\" mark(s) - 「{marked[0][:40]}」"
            )
        else:
            checks += 1

    return MarkedEnglishResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
