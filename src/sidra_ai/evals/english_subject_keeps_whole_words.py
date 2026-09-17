"""Does the page an English request produces name itself with whole words?

C-1913 found the English frame-stripper cutting into words and fixed the
line the verb runs through (`_EN_HEAD`). The defect was a *shape*, not a
line: `(?:a|an|the|some)?` is optional and carries no word boundary, and
alternation is leftmost-first, so 「an」 matches the `a` branch and leaves
its 「n」 standing - and a subject that merely BEGINS with an article loses
its first letter.

Two more lines had that shape, on two different surfaces, and both were
live when this was written:

  * `vocabulary._EN_SUBJECT` lifts the subject out from behind 「of」 /
    「about」 / 「featuring」 - art, decks, documents, gifs and models3d
    all pass through it. 「make art of an owl」 titled its page 「n owl」.
  * `games._STRIP_EN_ABOUT` does the same job for game pages. 「make a
    game about an octopus」 titled itself 「n octopus」.

So this judge reads the **title the finished page carries**, not the
helper that computes it - `<title>` out of `generate_art(...).html` and
`generate_game(...).html`. The helper is one refactor away from not being
the thing on screen, and C-1907 and C-1908 put this same string into the
canvas fallback and the live region, where a screen reader says it aloud.

The rule a frame-stripper cannot honestly break:

  **every word of the title is a whole word of the request.**

Checked in both directions, because a stripper that returned the request
untouched would satisfy that perfectly on its own:

  (a) no title word is a fragment - each appears as a word of the request;
  (b) the frame really came off - no verb, article or artifact noun that
      the request opened with survives into the title;
  (c) the title is the subject the request named, so a stripper cannot buy
      (a) and (b) by returning something shorter and wrong.

And the table is checked before the cases are, because dropping the case
that breaks is the cheapest route to a clean sheet: each surface must
carry the 「an」 shape AND a subject that merely starts with 「a」.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: (request, the subject the page should be titled). Per surface, because
#: the two roots are different lines in different modules and a table that
#: only exercised one would call the other green without reading it.
ART_CASES: tuple[tuple[str, str], ...] = (
    # 「an」 eaten down to its 「n」
    ("make art of an owl", "owl"),
    ("draw a picture of an elephant", "elephant"),
    ("make art about an island", "island"),
    # a subject that merely begins with the letters of an article
    ("make art of abstract shapes", "abstract shapes"),
    ("make art of anime clouds", "anime clouds"),
    ("make art about somebody", "somebody"),
    # and the shapes that already worked, which must keep working
    ("make art of a cat", "cat"),
    ("make art of the sea", "sea"),
    ("make art of some waves", "waves"),
)

GAME_CASES: tuple[tuple[str, str], ...] = (
    ("make a game about an octopus", "octopus"),
    ("make a racing game with an alien", "alien"),
    ("make a game about abstract shapes", "abstract shapes"),
    ("make a game about anime robots", "anime robots"),
    ("make a game about a robot", "robot"),
    ("make a game about the moon", "moon"),
)

#: What the request opens with and the title must not keep. The artifact
#: nouns are in here because 「make art of a cat」 is titled 「cat」, not
#: 「art of a cat」 - keeping the noun is the other way this strip fails.
FRAME_WORDS = frozenset(
    {
        "make", "create", "build", "generate", "design", "produce", "draw",
        "write", "model", "please", "give", "me", "let", "us",
        "a", "an", "the", "some", "another",
        "of", "about", "with", "featuring", "starring", "showing",
        "art", "picture", "game", "gif", "deck", "report", "app",
    }
)

_ARTICLES = frozenset({"a", "an", "the", "some"})
_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


@dataclass(frozen=True)
class EnglishSubjectResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _page_title(html: str) -> str:
    found = _TITLE.search(html or "")
    return found.group(1).strip() if found else ""


def _table_covers(cases: tuple[tuple[str, str], ...], surface: str) -> list[str]:
    """Both broken shapes have to be in the table, or the sheet is worthless."""

    complaints: list[str] = []
    if not any(re.search(r"\ban\b", request) for request, _ in cases):
        complaints.append(
            f"{surface}: no case uses the article 「an」 - the shape that left an 「n」 behind"
        )
    # Read the REQUEST, not the subject. 「with an alien」 has a subject that
    # begins with 「a」, but an article is sitting in front of it, so it only
    # exercises the 「an」 case again - a table holding nothing but that shape
    # passed this check while the letter-eating shape went untested (found by
    # sabotage D5, the same hole C-1896 D4 had). The shape wanted here is a
    # subject that begins with an article's spelling and has NO article of
    # its own to take: 「about anime robots」.
    bare = []
    for request, subject in cases:
        first = subject.lower().split()[0] if subject.split() else ""
        if not first.startswith(("a", "the", "some")) or first in _ARTICLES:
            continue
        words = [w.lower() for w in _WORD.findall(request)]
        if first in words and words[words.index(first) - 1] not in _ARTICLES:
            bare.append(request)
    if not bare:
        complaints.append(
            f"{surface}: no case has a subject that BEGINS with an article's "
            "letters and carries no article of its own - the shape that lost "
            "its first letter"
        )
    return complaints


def evaluate_english_subject_keeps_whole_words() -> EnglishSubjectResult:
    from sidra_ai.creation.art import generate_art
    from sidra_ai.creation.games import generate_game

    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    for cases, surface in ((ART_CASES, "art"), (GAME_CASES, "game")):
        complaints = _table_covers(cases, surface)
        failures.extend(complaints)
        if not complaints:
            checks += 1

    surfaces = (
        ("art", ART_CASES, lambda request: generate_art(request).html),
        ("game", GAME_CASES, lambda request: generate_game(request).html),
    )

    for surface, cases, render in surfaces:
        for request, subject in cases:
            try:
                title = _page_title(render(request))
            except Exception as err:  # a page that will not render has no title
                failures.append(f"{surface}「{request}」: page did not render ({err})")
                continue

            if not title:
                failures.append(f"{surface}「{request}」: the page carries no <title>")
                continue

            had = {word.lower() for word in _WORD.findall(request)}

            # (a) every word on the page is a whole word of the request
            cut = [w for w in _WORD.findall(title) if w.lower() not in had]
            if cut:
                failures.append(
                    f"{surface}「{request}」→「{title}」: "
                    f"{'・'.join(cut)} is not a word of the request"
                )
            else:
                checks += 1

            # (b) and the frame really came off
            left = [w.lower() for w in _WORD.findall(title) if w.lower() in FRAME_WORDS]
            if left:
                failures.append(
                    f"{surface}「{request}」→「{title}」: "
                    f"the frame word {'・'.join(left)} survived"
                )
            else:
                checks += 1

            # (c) and it is the subject that was named
            if title.lower() != subject:
                failures.append(
                    f"{surface}「{request}」→「{title}」, wanted 「{subject}」"
                )
            else:
                checks += 1

            readings.append(f"{surface}「{request}」→「{title}」")

    return EnglishSubjectResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
