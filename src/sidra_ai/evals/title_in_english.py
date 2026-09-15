"""Is an English request titled by its subject, or by its own sentence?

C-1841. Japanese ends with the making verb, so every generator's split takes
it off; English begins with it, and only ``games`` had a rule (C-1516 onward).
Measured across fifteen English requests before this: twelve titles carried
the sentence - a deck called 「make a slide deck about the new product」, a
report called 「write a report about monetisation」, a GIF called 「make a gif of
a fish」.

``drop_english_frame`` lives in ``vocabulary`` and is called by art, decks,
documents, gifs and models3d. The last of those had its own copy from C-1839
and now calls the shared one, so this removes a duplication rather than adding
one; games keeps its own, entangled with the game vocabulary.

Both directions are held: the English titles, and the Japanese ones that must
not move - plus games, the generator that was already right.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sidra_ai.creation import models3d
from sidra_ai.creation.art import generate_art
from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.gifs import generate_gif
from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.creation.vocabulary import drop_size_phrases

_GRAMMAR = re.compile(r"\b(?:make|draw|write|create|please|a|an|the|some)\b|\d", re.I)

#: request -> the title it should get, per generator.
ENGLISH: tuple[tuple[str, str, str], ...] = (
    ("gif", "make a gif of a fish", "fish"),
    ("gif", "make a 30 frame gif", "gif"),
    ("art", "make art of the sea", "sea"),
    ("art", "draw a picture of a cat", "cat"),
    ("deck", "make a slide deck about the new product", "new product"),
    ("doc", "write a report about monetisation", "monetisation"),
    ("doc", "write a monetisation report", "monetisation"),
    ("3d", "make a 3D model of a fish", "fish"),
    ("3d", "make 3 3D models of a fish", "fish"),
)

#: Japanese titles that must come out of this unchanged.
JAPANESE: tuple[tuple[str, str, str], ...] = (
    ("game", "猫のゲームを作って", "猫"),
    ("gif", "魚のGIFを作って", "魚"),
    ("art", "海のアートを作って", "海"),
    ("deck", "新商品のスライドを作って", "新商品"),
    ("doc", "収益化のレポートを作って", "収益化"),
    ("doc", "競合分析のレポートを作って", "競合分析"),
    ("3d", "魚の3Dモデルを作って", "魚"),
    ("3d", "魚の3Dモデルを3つ作って", "魚"),
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
class TitleEnglishResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_title_in_english() -> TitleEnglishResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) no English title carries the request's grammar ----------------
    carried = [
        f"{kind}:{request}->{_title(kind, request)}"
        for kind, request, _expected in ENGLISH
        if _GRAMMAR.search(_title(kind, request))
    ]
    add(not carried, f"A: the sentence is still the title: {carried[:3]}")
    # --- (B) and each one is the subject that was named --------------------
    wrong = {
        request: _title(kind, request)
        for kind, request, expected in ENGLISH
        if _title(kind, request) != expected
    }
    add(not wrong, f"B: the subject was not lifted: {wrong}")
    # --- (C) games, the generator that was already right, is untouched -----
    add(_title("game", "make a game about a cat") == "cat"
        and _title("game", "please make a puzzle game") == "puzzle",
        "C: the game titles moved - that rule was not this cycle's to change")
    # --- (D) every Japanese title is unchanged -----------------------------
    moved = {
        request: _title(kind, request)
        for kind, request, expected in JAPANESE
        if _title(kind, request) != expected
    }
    add(not moved, f"D: a Japanese title moved: {moved}")
    # --- (E) the size behind the kind word, in Japanese too ----------------
    #     Measured while doing this: 「収益化のレポートを3ページで作って」 was
    #     titled 「収益化のレポートを3ページ」 - the size and the kind word both,
    #     because the kind strip is anchored to the end. Stated here because it
    #     is a Japanese title this cycle deliberately changed.
    add(_title("doc", "収益化のレポートを3ページで作って") == "収益化",
        f"E: titled {_title('doc', '収益化のレポートを3ページで作って')!r}")
    # --- (F) a size is a size; a number inside a subject is not ------------
    #     The second half is the other loop's case, and their test is what
    #     caught this cycle cutting it: 「5枚組の写真集」 is a photo book of five
    #     prints, and 「5枚」 came out of it. The rule now needs the phrase to
    #     close - in the particle that attached it, or at a boundary - so a
    #     number glued to the next word stays where the operator put it.
    add(drop_size_phrases("3 page") == ""
        and drop_size_phrases("page 3 of the report") == "page 3 of the report"
        and drop_size_phrases("5枚組の写真集") == "5枚組の写真集"
        and drop_size_phrases("300万円の予算") == "300万円の予算"
        and drop_size_phrases("5枚のスライド") == "スライド",
        "F: the size rule cut a number that belonged to the subject")
    # --- (G) a trailing please is not a subject ----------------------------
    add(_title("3d", "make a 3d model of a boat please") == "boat",
        "G: 「please」 is part of the title")
    # --- (H) one copy of the rule, not two ---------------------------------
    #     C-1839 gave models3d its own frame regexes; this cycle folded them
    #     into vocabulary. A generator that grows its own again would pass
    #     every check above while the copies drift apart, which is the whole
    #     reason vocabulary exists (C-1120).
    add(not hasattr(models3d, "_EN_HEAD"),
        "H: models3d has its own English frame again")
    # --- (I) an English request naming no subject takes the default --------
    add(_title("3d", "make a model") == "魚",
        f"I: titled {_title('3d', 'make a model')!r} with no subject named")

    return TitleEnglishResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["ENGLISH", "JAPANESE", "TitleEnglishResult", "evaluate_title_in_english"]
