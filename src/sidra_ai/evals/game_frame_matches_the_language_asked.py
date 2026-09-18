"""Is the game page's frame written in the language it was asked in?

C-1956, the fourth page of the family (deck C-1951, art C-1952, 3D preview
C-1953). C-1938 put the game's **summary** into the language of the request
and C-1944 gave the template registry an English ``how_to_play``; the page
itself stayed Japanese.

**The frame only, and the split is measured rather than assumed.** Of the
3,076 lines a game page has, 184 carry Japanese - and **174 of those are
comments inside ``<script>``**, this repository's design notes, which no
reader of the page ever sees. Eight lines are what a reader meets: the
subtitle, the substitution caveat, the canvas's fallback text (§36 - the
one sentence a screen reader is handed), the fullscreen button, the rotate
hint, the how-to-play line, the touch hint and the footer.

What the canvas *draws* - the HUD's 「得点」, the start screen's three
briefing lines per template, the losing strip - is product copy on the
scale of C-1945 and is its own item. 「急いで訳すくらいなら訳さないほうが
まし」.

So this eval reads the frame and says so, with the number that justifies
it. Ignoring ``<script>`` would be a way to hide leftovers if the script
held any of the page's own prose; it holds none today, and the day it does
the canvas-text item is where that is measured.

Rules (C-1941's three, as the other three pages use them): no Japanese in
the English frame outside the operator's own title, ``<html lang>`` telling
the truth, the frame still being a frame, and the Japanese page unchanged -
as a GUARD, never half the score (C-1939).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: Asks that earn the substitution caveat too: neither subject is a genre
#: this product builds, so the page must admit the default kind.
ENGLISH_ASK = "make a game about an owl"
JAPANESE_ASK = "ふくろうのゲームを作って"


@dataclass(frozen=True)
class GameFrameResult:
    sides_right: int
    sides_total: int = 2
    japanese_held: bool = True
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _frame(html: str) -> str:
    """The part of the page a reader sees, without the script."""

    start = html.find("<body")
    end = html.find("<script", start)
    return html[start:end if end > start else len(html)]


def evaluate_game_frame_matches_the_language_asked() -> GameFrameResult:
    from sidra_ai.creation.games import generate_game

    failures: list[str] = []
    readings: list[str] = []
    right = 0
    japanese_held = True

    english = generate_game(ENGLISH_ASK)
    frame = _frame(english.html).replace(english.title, " ")
    leftovers = [line for line in frame.splitlines() if _JAPANESE.search(line)]
    declared = re.search(r'<html[^>]*\blang="([a-z-]+)"', english.html)
    problems: list[str] = []
    if leftovers:
        problems.append(f"{len(leftovers)} lines of the frame are still Japanese")
    if not declared or declared.group(1) != "en":
        problems.append(
            f"the page declares lang={declared.group(1) if declared else 'nothing'}"
        )
    # Still a frame: the canvas and its fallback, the caveat, the how-to line
    # and the footer. A page that dropped them would be "in English" by the
    # first rule while saying less than the Japanese one - translation by
    # deletion, which C-1941's third rule exists to stop.
    for needed, what in (
        ("<canvas", "the canvas"),
        ("How to play:", "the canvas fallback sentence"),
        ('class="how"', "the how-to-play line"),
        ('class="tag"', "the subtitle"),
        ("<footer>", "the footer"),
    ):
        if needed not in english.html:
            problems.append(f"{what} is gone")
    readings.append(f"EN frame-ja-lines={len(leftovers)}")
    if problems:
        failures.append("English: " + "; ".join(problems))
    else:
        right += 1

    japanese = generate_game(JAPANESE_ASK)
    guard: list[str] = []
    declared_ja = re.search(r'<html[^>]*\blang="([a-z-]+)"', japanese.html)
    if not declared_ja or declared_ja.group(1) != "ja":
        guard.append("the Japanese page stopped declaring Japanese")
    for phrase in ("難易度", "遊び方:", "全画面にする", "SIDRA AI が生成"):
        if phrase not in japanese.html:
            guard.append(f"「{phrase}」 is gone from the Japanese page")
    readings.append(
        "JA frame-ja-lines="
        f"{len([l for l in _frame(japanese.html).splitlines() if _JAPANESE.search(l)])}"
    )
    if guard:
        japanese_held = False
        failures.append("Japanese: " + "; ".join(guard))
    else:
        right += 1

    return GameFrameResult(
        sides_right=right if japanese_held else 0,
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["GameFrameResult", "evaluate_game_frame_matches_the_language_asked"]
