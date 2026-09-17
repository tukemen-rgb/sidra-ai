"""Does stripping the English frame ever cut into a word?

`drop_english_frame` takes 「make a picture of the sea」 down to 「sea」, and
five generators use it - art, decks, documents, gifs, models3d - so the
title of an English request passes through it on the way to the page.

It was cutting letters off. The article pattern `(?:a|an|the|some)?`
carries no word boundary, and alternation is leftmost-first, so 「an」
matched the `a` branch and left its 「n」 standing: 「draw an abstract
picture」 was titled 「n abstract picture」 and 「create an artwork」 became
「n artwork」. Worse, a subject that merely STARTS with a or an lost its
first letter - 「make abstract art」 became 「bstract art」, 「generate anime
wallpaper」 became 「nime wallpaper」.

It stayed invisible because the title still looked like a title: a page
headed 「n abstract picture」 renders, validates, and scores the same as
any other. C-1907 and C-1908 then put that string into the canvas's
fallback content and the live region, so a screen reader reads it aloud.

The rule this checks is the one the stripper cannot honestly break:

  **whatever comes out is made of whole words from what went in.**

A frame-stripper may drop words, reorder nothing, and keep the rest - so
every word of the output must appear as a word of the input. That holds
for Japanese requests too, and it is what 「bstract」 violates while
「abstract art」 does not.

Both directions, because a stripper that returned its input untouched
would satisfy the rule perfectly:

  (a) no output word is a fragment of an input word;
  (b) the frame is still being removed - the verb and article the request
      opens with are gone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Requests whose subject would lose a letter to an unbounded article, and
#: what the subject is. The first three are the 「an」 case, the next two
#: are a subject merely starting with a/an, and the rest are the shapes
#: that already worked and must keep working.
CASES: tuple[tuple[str, str], ...] = (
    ("draw an abstract picture", "abstract picture"),
    ("make an image", "image"),
    ("create an artwork", "artwork"),
    ("make abstract art", "abstract art"),
    ("generate anime wallpaper", "anime wallpaper"),
    ("make a picture", "picture"),
    ("build the sea", "sea"),
    ("design some flowers", "flowers"),
    ("give me a chart", "chart"),
    ("please make an app", "app"),
)

#: The words a request opens with that must not survive into the subject.
FRAME_WORDS = frozenset(
    {"make", "create", "build", "generate", "design", "produce", "draw",
     "write", "model", "please", "give", "me", "a", "an", "the", "some"}
)

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


@dataclass(frozen=True)
class EnglishFrameResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def evaluate_english_frame_keeps_whole_words() -> EnglishFrameResult:
    from sidra_ai.creation.vocabulary import drop_english_frame

    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    # The table has to keep the shapes that break. Dropping a case is
    # otherwise a way to a clean sheet with a smaller number - the hole
    # C-1891, C-1892, C-1896, C-1898 and C-1900 each had to close.
    starts_with_article_letter = [
        r for r, _ in CASES
        if any(w.lower().startswith(("a",)) and w.lower() not in {"a", "an"}
               for w in _WORD.findall(r)[1:])
    ]
    article_an = [r for r, _ in CASES if re.search(r"\ban\b", r)]
    if not starts_with_article_letter:
        failures.append(
            "no case has a subject beginning with 'a' - the shape that lost "
            "its first letter is not covered"
        )
    elif not article_an:
        failures.append("no case uses the article 「an」 - the shape that left an 'n' behind")
    else:
        checks += 1

    for request, subject in CASES:
        got = drop_english_frame(request)
        had = {w.lower() for w in _WORD.findall(request)}

        # (a) every word that came out is a word that went in
        cut = [w for w in _WORD.findall(got) if w.lower() not in had]
        if cut:
            failures.append(
                f"「{request}」 → 「{got}」: {'・'.join(cut)} is not a word of the request"
            )
        else:
            checks += 1

        # (b) and the frame really came off
        left = [w.lower() for w in _WORD.findall(got) if w.lower() in FRAME_WORDS]
        if left:
            failures.append(
                f"「{request}」 → 「{got}」: the frame word {'・'.join(left)} survived"
            )
        else:
            checks += 1

        # the subject itself, so a stripper that merely avoids fragments by
        # returning something shorter still has to return the right thing
        if got.strip().lower() != subject:
            failures.append(f"「{request}」 → 「{got}」, wanted 「{subject}」")
        else:
            checks += 1
        readings.append(f"「{request}」→「{got}」")

    return EnglishFrameResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
