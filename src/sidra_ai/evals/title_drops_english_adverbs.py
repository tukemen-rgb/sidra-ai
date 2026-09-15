"""Does an English request's 「right now」 end up as the artifact's name?

C-1842. English puts these words at the end - 「make a racing game right now」 -
and measured across five of them and six generators, all 30 titles kept the
adverb. The Japanese equivalents have come off since C-1829; REQUEST_ADVERBS
was Japanese vocabulary only.

One table serves both paths: ``drop_english_frame`` for the five generators
that call it, and games' own ``_STRIP_EN_TAIL``, which is built from the same
list rather than given a second one.

The boundary is the interesting part and is held here twice. Taking the tail
off before the subject is lifted turns 「write a report about today」 into
「report about」 - the adverb rule eating the word 「about」 points at - and with
the order fixed, that request lifts to 「today」, which must then survive,
because a rule that empties a title has stopped reading the request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sidra_ai.creation.art import generate_art
from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.gifs import generate_gif
from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.creation.vocabulary import (
    ENGLISH_REQUEST_ADVERBS,
    drop_english_frame,
)

ADVERBS: tuple[str, ...] = ("right now", "quickly", "asap", "today", "when you can")

#: generator -> the request shape the adverb is appended to, and the subject.
SHAPES: tuple[tuple[str, str, str], ...] = (
    ("game", "make a racing game {}", "racing"),
    ("gif", "make a gif of a fish {}", "fish"),
    ("art", "make art of the sea {}", "sea"),
    ("deck", "make a slide deck about sales {}", "sales"),
    ("doc", "write a report about sales {}", "sales"),
    ("3d", "make a 3d model of a fish {}", "fish"),
)


def _title(kind: str, request: str) -> str:
    if kind == "game":
        return generate_game(request).title
    if kind == "gif":
        return generate_gif(request).title
    if kind == "art":
        return generate_art(request).title
    if kind == "deck":
        return generate_deck(request).title
    if kind == "doc":
        return generate_document(request).title
    return generate_model3d(request).title


@dataclass(frozen=True)
class EnglishAdverbResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_title_drops_english_adverbs() -> EnglishAdverbResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    kept = [
        f"{kind}:{adverb}->{_title(kind, shape.format(adverb))}"
        for kind, shape, _subject in SHAPES
        for adverb in ADVERBS
        if adverb.split()[0] in _title(kind, shape.format(adverb)).lower()
    ]
    # --- (A) none of the thirty keeps its adverb --------------------------
    add(not kept, f"A: the adverb is still the artifact's name: {kept[:4]}")
    # --- (B) and each title is the subject that was named -----------------
    wrong = {
        shape.format(adverb): _title(kind, shape.format(adverb))
        for kind, shape, subject in SHAPES
        for adverb in ADVERBS
        if _title(kind, shape.format(adverb)) != subject
    }
    add(not wrong, f"B: the subject did not survive: {list(wrong.items())[:3]}")
    # --- (C) a subject that IS one of these words survives ----------------
    #     「write a report about today」 is a report about today.
    add(_title("doc", "write a report about today") == "today",
        f"C: titled {_title('doc', 'write a report about today')!r}")
    # --- (D) and one that contains it, not at the end, is untouched -------
    possessive = _title("doc", "write a report about today's sales")
    add(possessive == "today's sales", f"D: titled {possessive!r}")
    # --- (E) two stacked adverbs both come off ----------------------------
    add(_title("game", "make a racing game quickly right now") == "racing",
        "E: only the outer adverb came off")
    # --- (F) English requests with no adverb are unchanged ----------------
    add(_title("game", "make a racing game") == "racing"
        and _title("game", "please make a puzzle game") == "puzzle"
        and _title("gif", "make a gif of a fish") == "fish",
        "F: an English request with no adverb changed its title")
    # --- (G) Japanese is unchanged ----------------------------------------
    add(_title("game", "猫のゲームを作って") == "猫"
        and _title("doc", "収益化のレポートを作って") == "収益化"
        and _title("gif", "魚のGIFを作って") == "魚",
        "G: a Japanese title moved")
    # --- (H) one table, read by both paths --------------------------------
    #     games has its own tail rule and keeps it; what it must not have is
    #     its own list, which is how two tables drift apart (C-1120).
    import sidra_ai.creation.games as games_module

    missing = [
        word
        for word in ENGLISH_REQUEST_ADVERBS
        # re.escape is what built the pattern, spaces included: 「right now」
        # lives in it as 「right\ now」, which is what caught this check being
        # written against the unescaped words.
        if re.escape(word) not in games_module._STRIP_EN_TAIL.pattern
    ]
    add(not missing and drop_english_frame("make a gif of a fish right now") == "fish",
        f"H: games no longer reads the shared table: {missing[:4]}")
    # --- (I) the table's own admission test --------------------------------
    #     Every row has to be deletable from a request without changing what
    #     gets made; a word that names a thing would fail that.
    add(all(
            drop_english_frame(f"make a gif of a fish {word}") == "fish"
            for word in ENGLISH_REQUEST_ADVERBS
        ),
        "I: a row in the table does not behave like an adverb")

    return EnglishAdverbResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "ADVERBS",
    "EnglishAdverbResult",
    "SHAPES",
    "evaluate_title_drops_english_adverbs",
]
