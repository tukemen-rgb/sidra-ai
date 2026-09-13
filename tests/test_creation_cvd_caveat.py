"""利用者が選べる色にも、色覚の床がある (§20 × §4, C-1756).

``creation_cvd_info_pair`` (C-1369) holds this product's four palettes to
a separation between its two information hues - the accent that marks
headings and the alert that marks danger - under each of three
dichromacies, simulated with Machado's full-severity matrices. It
measured the palettes and nothing else.

Every colour a person can choose went unmeasured: the eight colour words,
and the three colours a score unlocks. Of the 132 cells they reach (11
colours × 4 themes × 3 dichromacies) **14 fall under the floor**. The
worst is 「桃」 on dusk at ΔE 8.5 against a floor of 20 - for a
protanope, the HUD's headings and 「のこり N」 are one colour.

This is the same one-sided rule C-1737 found on the contrast side of the
same control: enforced where the product picks, unmeasured where the
person does.

**The colour is not moved for it.** Nudging brightness keeps the colour
somebody asked for; nudging hue does not, and 「桃にして」 answered in
another hue is not their page any more. What the product owes them is the
fact, at the moment they ask (C-1739).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.creation.games import generate_game, save_game
from sidra_ai.creation.revise import (
    _ACCENT_WORDS,
    _colour_caveat,
    build_game_reviser,
    detect_revision_intent,
    save_meta,
)
from sidra_ai.creation.skins import SKIN_COLOURS
from sidra_ai.creation.themes import (
    CVD_MATRICES,
    THEMES,
    cvd_collisions,
    cvd_distance,
    cvd_floor,
)

CHOOSABLE = [(w, c) for w, c in _ACCENT_WORDS.items()] + [
    (label, colour) for _ident, label, colour in SKIN_COLOURS if colour
]
CELLS = [(t, w) for t in sorted(THEMES) for w, _c in CHOOSABLE]


def test_the_simulator_still_simulates() -> None:
    """C-1369's sentinel, moved here with the measurement it guards.

    A red and a dark yellow are far apart to most eyes and close for a
    protanope. If that stops being true, the matrices are not simulating
    and every passing cell below is a blessing from a broken instrument.
    """

    raw = cvd_distance("#ff0000", "#9b9b00", "protan")
    assert raw < 40.0, raw


def test_the_floors_are_the_ones_the_themes_are_held_to() -> None:
    assert cvd_floor("gameyard") == 15.0
    for key in THEMES:
        if key != "gameyard":
            assert cvd_floor(key) == 20.0, key
    assert set(CVD_MATRICES) == {"protan", "deutan", "tritan"}


def test_some_choosable_colours_really_do_collapse() -> None:
    """The measurement this item is about, kept where it can be read."""

    collapsed = [
        (theme, name, kind, round(apart, 1))
        for theme in sorted(THEMES)
        for name, colour in CHOOSABLE
        for kind, apart in cvd_collisions(colour, theme)
    ]
    assert len(collapsed) == 14, collapsed
    assert ("dusk", "桃", "protan", 8.5) in collapsed, collapsed


@pytest.mark.parametrize("theme,word", CELLS, ids=[f"{t}-{w}" for t, w in CELLS])
def test_the_caveat_speaks_exactly_when_the_hues_collapse(
    theme: str, word: str, tmp_path: Path
) -> None:
    colour = dict(CHOOSABLE)[word]
    hit = cvd_collisions(colour, theme)
    if word in _ACCENT_WORDS:
        built = generate_game("冒険ゲームを作って", template="adventure", theme_name=theme)
        page = save_game(built, str(tmp_path))
        save_meta(
            page,
            request="冒険ゲームを作って",
            template="adventure",
            difficulty=built.difficulty,
            theme=theme,
            title=built.title,
            panel={},
        )
        line = f"冒険ゲームを{word}にして"
        intent = detect_revision_intent(line)
        assert intent.is_revision, line
        said = str(getattr(build_game_reviser(str(tmp_path))(line, intent), "summary", ""))
    else:
        # A skin is not reachable by a sentence; the same caveat carries
        # it, and the panel's own note (C-1747) is what a player sees.
        said = _colour_caveat(colour, theme)
    spoke = "見分けにくく" in said
    assert spoke == bool(hit), (theme, word, hit, said)
    if hit:
        worst = min(apart for _kind, apart in hit)
        assert f"{worst:.1f}" in said, said


def test_all_three_collapsing_is_said_once(tmp_path: Path) -> None:
    """Three clauses saying the same thing is how a caveat stops being read."""

    said = _colour_caveat(_ACCENT_WORDS["桃"], "dusk")
    assert "どの色覚でも" in said, said
    assert said.count("見分けにくく") == 1, said


def test_a_colour_that_separates_says_nothing_about_eyes() -> None:
    assert "見分けにくく" not in _colour_caveat(_ACCENT_WORDS["青"], "dusk")


def test_the_hue_is_never_moved_for_this() -> None:
    """The caveat reports; it does not rewrite the request."""

    said = _colour_caveat(_ACCENT_WORDS["桃"], "dusk")
    assert "#" not in said, said
    assert "寄せて" not in said, said
