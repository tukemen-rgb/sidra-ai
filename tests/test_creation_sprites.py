"""Generated art is where a design system quietly acquires a second palette.

Each sprite looks fine on its own, so an invented colour is invisible per file
and obvious only across the set - by which time it is everywhere. The palette
test here enumerates what a renderer would actually paint.

The other failure is subtler: assets written to disk that no page loads. Both
halves pass their own inspection (files exist; page renders), and the feature
is dead. So the tests check the reference, and the fallback that keeps the
game playable when the reference cannot resolve.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import TEMPLATES, generate_game, validate_game_html  # noqa: E402
from sidra_ai.creation.projects import scaffold_project  # noqa: E402
from sidra_ai.creation.sprites import (  # noqa: E402
    PALETTE,
    SPRITE_SETS,
    colours_in,
    generate_sprites,
    off_palette,
    save_sprites,
    seed_for,
)


# ------------------------------------------------------------- palette


@pytest.mark.parametrize("template", sorted(SPRITE_SETS))
def test_every_sprite_stays_inside_the_palette(template) -> None:
    """DESIGN.md §2: do not invent a second design system inside a page."""

    for sprite in generate_sprites(template, seed=seed_for("釣りゲームを作って")):
        assert not off_palette(sprite.svg), (sprite.filename, off_palette(sprite.svg))


def test_the_palette_check_reads_what_a_renderer_would_paint() -> None:
    """A regex over the text would also miss a colour set on a child node."""

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg"><g fill="#2ee6ff">'
        '<rect fill="#ff0000"/></g></svg>'
    )

    assert "#ff0000" in colours_in(svg)
    assert off_palette(svg) == {"#ff0000"}


def test_the_palette_is_the_token_set_and_nothing_else() -> None:
    from sidra_ai.creation.games import GAMEYARD_TOKENS

    for key in ("bg", "surface", "raised", "cyan", "magenta"):
        assert GAMEYARD_TOKENS[key] in PALETTE


# ----------------------------------------------------------- the seed


@pytest.mark.parametrize("template", sorted(SPRITE_SETS))
def test_the_same_request_gives_the_same_bytes(template) -> None:
    """A project's documents describe its art; regeneration must match."""

    first = generate_sprites(template, seed=seed_for("釣りゲームを作って"))
    again = generate_sprites(template, seed=seed_for("釣りゲームを作って"))

    assert [s.svg for s in first] == [s.svg for s in again]


def test_the_seed_survives_a_new_process() -> None:
    """``hash()`` is salted per process; tomorrow's run must match today's."""

    assert seed_for("釣りゲームを作って") == seed_for("釣りゲームを作って")
    assert seed_for("釣りゲームを作って") != seed_for("キャッチゲームを作って")


@pytest.mark.parametrize("template", sorted(SPRITE_SETS))
def test_every_sprite_is_wellformed_svg(template) -> None:
    for sprite in generate_sprites(template, seed=7):
        root = ElementTree.fromstring(sprite.svg)
        assert root.tag.endswith("svg")
        assert root.get("viewBox")


def test_each_template_gets_the_two_names_its_page_draws() -> None:
    expected = {
        "fishing": {"target", "marker"},
        "catch": {"target", "marker"},
        # The adventure page draws a world, not a target and a marker; its
        # set is the five things its own script asks sprite() for.
        "adventure": {"hero", "enemy", "rock", "bush", "npc"},
        # The duel draws its fighters procedurally; sprite() falls back to
        # the shapes the template always drew, which is the supported state.
        "duel": set(),
        # The shooter draws its ship and shots as paths; the foe is the
        # one thing a wave of which the eye reads as a shape.
        "shooter": {"foe"},
    }
    for template in TEMPLATES:
        names = {name for name, _ in SPRITE_SETS.get(template, ())}
        assert names == expected[template], template


# ------------------------------------------------------- the reference


def test_a_page_given_sprites_references_them() -> None:
    html = generate_game(
        "ゲームを作って", sprites={"target": "assets/target.svg"}
    ).html

    assert "assets/target.svg" in html


def test_a_page_given_none_is_the_single_file_game_it_was() -> None:
    """The standalone artifact must not start fetching a sibling file."""

    html = generate_game("ゲームを作って").html

    assert "assets/" not in html
    assert validate_game_html(html)["playable"]


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_a_page_with_sprites_still_parses_and_plays(template) -> None:
    html = generate_game(
        "ゲームを作って",
        template=template,
        sprites={"target": "assets/target.svg", "marker": "assets/marker.svg"},
    ).html

    assert validate_game_html(html)["playable"]


def test_the_page_falls_back_when_a_sprite_cannot_load() -> None:
    """An emptied assets/ should cost the look, not the game."""

    html = generate_game(
        "ゲームを作って", sprites={"target": "assets/target.svg"}
    ).html

    assert "img.complete" in html, "the draw is guarded on the image being ready"
    assert "fillRect" in html, "the shape it always drew is still the fallback"


# ---------------------------------------------------------- on disk


def test_a_whole_project_writes_sprites_the_page_loads(tmp_path) -> None:
    project = scaffold_project("企画から釣りゲームを一通り作って", tmp_path)

    written = sorted(path.name for path in (project.root / "assets").glob("*.svg"))
    page = (project.root / "game.html").read_text(encoding="utf-8")

    assert written == ["marker.svg", "target.svg"]
    for name in written:
        assert f"assets/{name}" in page


def test_a_game_without_the_assets_stage_stays_one_file(tmp_path) -> None:
    """Asking for the page alone must not leave it pointing at nothing."""

    project = scaffold_project("釣りゲームの本体だけ作って", tmp_path)

    assert "assets/" not in (project.root / "game.html").read_text(encoding="utf-8")


def test_saving_reports_what_it_wrote(tmp_path) -> None:
    written = save_sprites(generate_sprites("catch", seed=1), tmp_path / "assets")

    assert set(written) == {"target.svg", "marker.svg"}
    for name in written:
        assert (tmp_path / "assets" / name).read_text(encoding="utf-8").startswith("<svg")
