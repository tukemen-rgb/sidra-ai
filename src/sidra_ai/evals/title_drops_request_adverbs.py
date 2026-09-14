"""Does a title name the thing asked for, or the sentence that asked for it?

C-1829. Every title builder cuts the request at its making verb, so a word
sitting between the artifact noun and that verb survived - and it also turned
off the strip that takes the kind word off the end, because that one is
anchored to the end. Measured across eight adverbs and six generators before
the fix: **47 of 48 titles carried the request's own grammar**, including
「猫のゲームを今すぐ」 and 「魚のGIFを急い」, the last cut inside its okurigana.

For a whole production the name lands in six files, the ``<title>`` and
``<h1>`` of the playable page among them.

English already had this rule (``_STRIP_EN_TAIL``: please / thanks / for my
kid, C-1528 and C-1531). The Japanese side knew ください and ほしい and no
adverbs, so the list now lives in ``vocabulary`` where every generator reads
it.

Both directions are held here. A guard that removed too much would score
perfectly on the first half: 「ざっくりしたアート」 says what the artifact should
be like, and a title that dropped it would quote less than was asked for.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.art import generate_art
from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.gifs import generate_gif
from sidra_ai.creation.projects import _title_from as project_title

#: Eight of the words, across the six generators that build a title.
ADVERBS: tuple[str, ...] = (
    "今すぐ", "まとめて", "ちゃんと", "サクッと",
    "とりあえず", "急いで", "早めに", "できれば",
)

#: request shape -> (title of what was built, the kind words it must not echo)
SHAPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "game": ("猫のゲームを{}作って", ("ゲーム",)),
    "gif": ("魚のGIFを{}作って", ("GIF",)),
    "art": ("海のアートを{}作って", ("アート",)),
    "deck": ("新商品のスライドを{}作って", ("スライド",)),
    "doc": ("収益化のレポートを{}作って", ("レポート",)),
    # The scaffold makes a game project, so 「猫のゲーム」 is its right name and
    # only the production words would be an echo.
    "project": ("猫のゲームを企画から{}作って", ("制作一式", "プロジェクト", "一式")),
}


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
    return project_title(request)


@dataclass(frozen=True)
class TitleAdverbResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_title_drops_request_adverbs() -> TitleAdverbResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) not one of the 48 titles carries the adverb ------------------
    kept: list[str] = []
    echoed: list[str] = []
    for kind, (shape, nouns) in SHAPES.items():
        for adverb in ADVERBS:
            title = _title(kind, shape.format(adverb))
            if adverb in title:
                kept.append(f"{kind}:{adverb}->{title}")
            # --- (B) and the kind word the title must not echo is gone ----
            if any(noun in title for noun in nouns):
                echoed.append(f"{kind}:{adverb}->{title}")
    add(not kept, f"A: the adverb is still the artifact's name: {kept[:4]}")
    add(not echoed,
        f"B: the kind word rode along with the adverb: {echoed[:4]}")

    # --- (C) no title ends on a dangling particle -------------------------
    dangling = [
        title
        for kind, (shape, _nouns) in SHAPES.items()
        for title in [_title(kind, shape.format(adverb)) for adverb in ADVERBS]
        if title and title[-1] in "をのはがにで"
    ]
    add(not dangling, f"C: a title ends on a particle: {dangling[:4]}")

    # --- (D) the whole production's own phrasing, which had the same bug --
    #     via a different route: removing 「一式」 left a space, so the
    #     anchored particle strip matched nothing (5 of 14 requests).
    whole = project_title("レースゲームを企画から一式で作って")
    add(whole == "レースゲーム", f"D: the production is named {whole!r}")

    # --- (E) a word that describes the ARTIFACT is kept -------------------
    add("ざっくり" in _title("art", "ざっくりしたアートを作って"),
        "E: a word about what the artifact should be like was dropped")
    # --- (F) and one inside a subject is kept -----------------------------
    #     Only the tail is read, so 「今すぐ帰りたい人」 keeps its 今すぐ. Both
    #     routes are driven: the game path removes the word in front of the
    #     verb, the other five cut at the verb and then read the tail, and a
    #     rule that read the middle would be wrong in a different place in each.
    add("今すぐ" in _title("game", "今すぐ帰りたい人のゲームを作って")
        and "今すぐ" in _title("art", "今すぐ帰りたい人のアートを作って"),
        "F: an adverb inside the subject was taken out of the middle")
    # --- (G) an ordinary request is untouched -----------------------------
    add(_title("game", "猫のゲームを作って") == "猫"
        and _title("gif", "魚のGIFを作って") == "魚"
        and _title("deck", "新商品のスライドを作って") == "新商品",
        "G: a request with no adverb changed its title")
    # --- (H) two stacked adverbs both come off ----------------------------
    add(_title("game", "猫のゲームをとりあえず今すぐ作って") == "猫",
        "H: only the outer adverb came off")

    return TitleAdverbResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "ADVERBS",
    "SHAPES",
    "TitleAdverbResult",
    "evaluate_title_drops_request_adverbs",
]
