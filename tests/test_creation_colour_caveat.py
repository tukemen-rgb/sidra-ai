"""頼んだ色がそのテーマで使えないことを、頼んだその場で言う (C-1739).

§4 × §9 事実 2. The eight colour words (`赤`…`白`) are one fixed colour
each, chosen against a dark ground, and **all eight fall under this
product's own accent floor on the paper theme** - 白 at 1.09:1 against
`#f5f7fb`. C-1737 made the page lift such a colour to a readable strength
and print a note saying so, which is the right behaviour; what was
missing is that the note lives in the panel, and nobody reads the panel
until they have opened the page and found it wrong.

The person asked for the colour in a sentence. §9 事実 2 puts 「意図理解
の低さ」 second among the market's complaints, and answering 「白にして」
with a grey and saying nothing is exactly its shape.

The resulting colour is deliberately not recomputed on this side: the
page owns that rule, and a second implementation of it is the drift
C-1342 is about. What the summary needs is one comparison the product
already has.

Both directions. Saying it every time passes the first check on its own,
and 24 apologies for nothing is how a caveat stops being read.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sidra_ai.creation.games import generate_game, save_game
from sidra_ai.creation.revise import (
    _ACCENT_WORDS,
    build_game_reviser,
    detect_revision_intent,
    save_meta,
)
from sidra_ai.creation.themes import ACCENT_FLOOR, THEMES, contrast_ratio

REQUEST = "冒険ゲームを作って"
CELLS = [(theme, word) for theme in sorted(THEMES) for word in _ACCENT_WORDS]


def _revise(home: Path, theme: str, word: str) -> str:
    built = generate_game(REQUEST, template="adventure", theme_name=theme)
    page = save_game(built, str(home))
    save_meta(
        page,
        request=REQUEST,
        template="adventure",
        difficulty=built.difficulty,
        theme=theme,
        title=built.title,
        panel={},
    )
    line = f"冒険ゲームを{word}にして"
    intent = detect_revision_intent(line)
    assert intent.is_revision, line
    assert intent.adjustments.get("accent") == _ACCENT_WORDS[word]
    out = build_game_reviser(str(home))(line, intent)
    return str(getattr(out, "summary", "") or out)


def test_the_paper_theme_really_is_the_hard_one() -> None:
    """The measurement this item is about, kept where it can be read."""

    under = {
        theme: [
            word
            for word, colour in _ACCENT_WORDS.items()
            if contrast_ratio(colour, THEMES[theme].tokens["surface"]) < ACCENT_FLOOR
        ]
        for theme in sorted(THEMES)
    }
    assert under["paper"] == list(_ACCENT_WORDS), under["paper"]
    for theme in sorted(THEMES):
        if theme != "paper":
            assert under[theme] == [], (theme, under[theme])


@pytest.mark.parametrize("theme,word", CELLS, ids=[f"{t}-{w}" for t, w in CELLS])
def test_the_summary_speaks_exactly_when_the_colour_sinks(
    theme: str, word: str, tmp_path: Path
) -> None:
    said = _revise(tmp_path, theme, word)
    ratio = contrast_ratio(_ACCENT_WORDS[word], THEMES[theme].tokens["surface"])
    assert "差し色" in said, said
    if ratio >= ACCENT_FLOOR:
        assert "沈む" not in said, f"読める色に言い訳をつけた: {said}"
    else:
        assert "沈む" in said, f"{ratio:.2f}:1 で沈むのに黙っている: {said}"
        # The measured number, not a vague line: a caveat that cannot be
        # checked against the page is the kind C-1722 threw out.
        assert f"{ratio:.2f}" in said, said
        assert theme in said, said


def test_white_on_paper_is_the_worst_cell_and_is_named(tmp_path: Path) -> None:
    """The cell that made this item: 「白にして」 answered with a grey."""

    said = _revise(tmp_path, "paper", "白")
    assert "1.09" in said, said


def test_a_colour_that_reads_is_reported_without_apology(tmp_path: Path) -> None:
    said = _revise(tmp_path, "gameyard", "白")
    assert said.count("差し色") == 1
    assert "沈む" not in said and "1.09" not in said, said


def test_the_caveat_does_not_claim_to_know_the_colour(tmp_path: Path) -> None:
    """The page decides the replacement; this side must not guess it.

    Two implementations of one rule is the drift C-1342 is about, so the
    sentence promises a readable strength and names no hex.
    """

    said = _revise(tmp_path, "paper", "緑")
    assert not re.search(r"#[0-9a-fA-F]{6}", said), said
