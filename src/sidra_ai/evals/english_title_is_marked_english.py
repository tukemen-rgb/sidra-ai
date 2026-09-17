"""Does a Japanese page tell the screen reader which words are English?

Every SIDRA page declares `<html lang="ja">`, which satisfies SC 3.1.1
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

What this reads is the **finished page**, not the helper: `generate_art`
and `generate_game` are driven and their HTML parsed (C-1640).

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
  (d) the page still declares `lang="ja"`. (a) is trivially satisfiable by
      flipping the document to English and breaking 3.1.1 instead.
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
)

#: The same two surfaces asked in Japanese. Nothing here may be marked.
JAPANESE_CASES: tuple[tuple[str, str], ...] = (
    ("game", "レースゲームを作って"),
    ("game", "釣りゲームを作って"),
    ("art", "海のアートを作って"),
    ("art", "螺旋のアートを作って"),
)

_JAPANESE_SCRIPT = re.compile(r"[぀-ゟ゠-ヿ一-鿿々ー]")
_SPAN_EN = re.compile(r'<span lang="en">(.*?)</span>', re.S)
_SCRIPTISH = re.compile(r"<script.*?</script>|<style.*?</style>", re.S)
_TITLE_EL = re.compile(r"<title>.*?</title>", re.S)
_HTML_TAG = re.compile(r"<html[^>]*>")


@dataclass(frozen=True)
class MarkedEnglishResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _render(surface: str, request: str) -> str:
    from sidra_ai.creation.art import generate_art
    from sidra_ai.creation.games import generate_game

    return (generate_game if surface == "game" else generate_art)(request).html


def _displayed(html: str) -> str:
    """The page with its scripts, styles and text-only <title> taken out."""

    return _TITLE_EL.sub("", _SCRIPTISH.sub("", html))


def evaluate_english_title_is_marked_english() -> MarkedEnglishResult:
    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    # The table first: a sheet that only asks English requests cannot catch a
    # marker that marks everything, and one that only asks Japanese cannot
    # catch a marker that marks nothing. Both surfaces need both.
    for surface in ("game", "art"):
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

        # (d) the document's own language is still declared, and still ja
        tag = _HTML_TAG.search(html)
        if not tag or 'lang="ja"' not in tag.group(0):
            failures.append(
                f"{surface}「{request}」: the document no longer declares "
                f"lang=\"ja\" ({tag.group(0) if tag else 'no <html> tag'})"
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
