"""A generated game has to run on the machine that generated it.

The failure this file exists to prevent is a page that looks finished and does
nothing: a script that never parsed, a canvas that was never added, a font
pulled from a CDN that is unreachable on a loopback-bound host. Each of those
is silent in a screenshot, so each gets an assertion.

The second theme is the identity. ``docs/DESIGN.md`` §3 lists defaults that are
prohibited *because* they are what a generator reaches for by itself - emoji as
icons, purple-to-blue gradients, a new font dependency. A generator is exactly
the thing that would reintroduce them, so they are pinned here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation import (  # noqa: E402
    GAMEYARD_TOKENS,
    TEMPLATES,
    generate_game,
    validate_game_html,
)
from sidra_ai.creation.share import SHARE_EMOJI  # noqa: E402
from sidra_ai.creation.games import (  # noqa: E402
    choose_difficulty,
    choose_template,
    save_game,
)


# ------------------------------------------------------------- it runs


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_every_template_produces_a_playable_page(key) -> None:
    result = validate_game_html(generate_game("ゲームを作って", template=key).html)

    assert result["playable"], result["failures"]


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_every_template_fetches_nothing(key) -> None:
    """No CDN font, no external script. The operator's host is loopback-bound."""

    html = generate_game("ゲームを作って", template=key).html

    assert "http://" not in html
    assert "https://" not in html
    assert "@import" not in html


def test_at_least_two_templates_exist() -> None:
    """One template is a demo; the second is what makes it a generator."""

    assert len(TEMPLATES) >= 2


# ------------------------------------------------- reading the request


def test_the_named_game_is_the_one_generated() -> None:
    assert choose_template("釣りゲームを作って") == "fishing"
    assert choose_template("キャッチゲームを作って") == "catch"


def test_an_unnamed_game_still_generates_something() -> None:
    """"ゲームを作って" is a real request. Refusing it would be the bug."""

    assert choose_template("ゲームを作って") in TEMPLATES


@pytest.mark.parametrize(
    "request_text,expected",
    [
        ("難しい釣りゲームを作って", "hard"),
        ("難しくして", "hard"),
        ("簡単な釣りゲームを作って", "easy"),
        ("やさしい釣りゲームを作って", "easy"),
        ("釣りゲームを作って", "normal"),
    ],
)
def test_difficulty_words_reach_the_game(request_text, expected) -> None:
    """Wording that changes only the tagline would be cosmetic compliance."""

    assert choose_difficulty(request_text) == expected


def test_difficulty_changes_the_numbers_not_just_the_label() -> None:
    easy = generate_game("簡単な釣りゲームを作って").html
    hard = generate_game("難しい釣りゲームを作って").html

    assert easy != hard
    # The band the player has to hit is the difficulty; if these matched, the
    # two pages would play identically whatever the tagline claimed.
    assert "0.34" in easy and "0.12" in hard


def test_the_operators_own_words_become_the_title() -> None:
    assert generate_game("マグロ釣りを作って").title == "マグロ釣り"


def test_an_essay_does_not_become_the_title(  ) -> None:
    """A long request is context, not a name; fall back to the template's."""

    long_request = "うちの新しいキャンペーン向けに" * 4 + "釣りゲームを作って"

    assert generate_game(long_request).title == TEMPLATES["fishing"].default_title


# ------------------------------------------------------------ identity


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_the_page_uses_gameyard_tokens(key) -> None:
    html = generate_game("ゲームを作って", template=key).html

    assert GAMEYARD_TOKENS["bg"] in html
    assert GAMEYARD_TOKENS["cyan"] in html


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_prohibited_defaults_stay_out(key) -> None:
    """DESIGN.md §3, the entries a generator would reach for unprompted."""

    html = generate_game("ゲームを作って", template=key).html.lower()

    assert "linear-gradient" not in html, "no decorative gradient (§3)"
    assert "backdrop-filter" not in html, "no glassmorphism (§3)"
    assert "box-shadow" not in html, "no glow or drop shadow (§3)"
    assert "fonts.googleapis" not in html, "no new font CDN (§3)"


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_the_only_emoji_in_the_page_is_the_one_you_paste(key) -> None:
    """§3's ban is on emoji **as interface icons** (docs/OUTCOMES.md), and
    that stands: no button, label or heading carries one.

    The one place the knowledge base asks for them by name is the copied
    result - §8 事実 7 records that Wordle's spread ran on an emoji grid
    with no URL in it - so C-1110's row is the single exception, and it is
    pinned rather than merely allowed: the mark appears exactly once in
    the page, in the share spec the copied line is built from, and never
    anywhere a person can see it in the interface.
    """

    html = generate_game("ゲームを作って", template=key).html
    mark = SHARE_EMOJI[key]

    strays = {ch for ch in html if ord(ch) > 0x1F000} - set(mark)
    assert not strays, f"emoji used as an icon (§3): {strays}"
    assert html.count(mark) == 1, "the share mark is drawn in the interface too"


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_the_page_says_where_its_design_came_from(key) -> None:
    html = generate_game("ゲームを作って", template=key).html

    assert "DESIGN.md" in html


def test_supplied_evidence_replaces_the_default_citation() -> None:
    html = generate_game("ゲームを作って", evidence=["site docs/DESIGN.md @abc123"]).html

    assert "abc123" in html


# ----------------------------------------------------------- validator


def test_a_page_without_a_canvas_is_not_playable() -> None:
    html = generate_game("ゲームを作って").html.replace("<canvas", "<div")

    result = validate_game_html(html)

    assert not result["playable"]
    assert any("canvas" in f for f in result["failures"])


def test_a_page_whose_script_does_not_parse_is_not_playable() -> None:
    """The failure a screenshot cannot show."""

    html = generate_game("ゲームを作って").html.replace("step();", "step(;")

    result = validate_game_html(html)

    assert not result["playable"]
    assert any("javascript" in f for f in result["failures"])


def test_an_external_asset_is_a_failure() -> None:
    html = generate_game("ゲームを作って").html.replace(
        "</head>", '<link href="https://fonts.googleapis.com/x" rel="stylesheet"></head>'
    )

    result = validate_game_html(html)

    assert not result["playable"]
    assert any("external" in f for f in result["failures"])


def test_the_validator_names_the_checker_it_used() -> None:
    """"playable" measured by a checker that silently downgraded is a lie."""

    result = validate_game_html(generate_game("ゲームを作って").html)

    assert result["js_checker"]
    assert result["js_checker"] != "not run"


def test_every_failure_is_reported_not_just_the_first() -> None:
    html = generate_game("ゲームを作って").html.replace("<canvas", "<div").replace(
        "step();", "step(;"
    )

    assert len(validate_game_html(html)["failures"]) >= 2


# --------------------------------------------------------- model copy


def test_model_copy_is_an_overlay_on_a_page_that_already_works() -> None:
    game = generate_game("釣りゲームを作って")

    improved = game.with_copy(title="早朝の堤防", tagline="潮が動く前に一本。")

    assert "早朝の堤防" in improved.html
    assert validate_game_html(improved.html)["playable"]


def test_an_empty_model_answer_leaves_the_page_intact() -> None:
    """No weights is the default configuration, not an error path."""

    game = generate_game("釣りゲームを作って")

    assert game.with_copy(title="  ", tagline="") is game


# --------------------------------------------------------------- disk


def test_the_artifact_is_written_locally(tmp_path) -> None:
    game = generate_game("釣りゲームを作って")

    path = save_game(game, tmp_path)

    assert path.parent == tmp_path / "artifacts"
    assert path.read_text(encoding="utf-8") == game.html


# ----------------------------------------------- the router's evidence


def test_the_generator_survives_the_evidence_the_router_hands_it(tmp_path) -> None:
    """The crash this file did not catch the first time.

    The generator reached for fields ``Fact`` does not have, so any creation
    request that retrieved something raised ``AttributeError`` and returned
    500 - while every test here passed, because none of them handed it a
    fact. A citation line is the least important part of the page and it was
    taking the whole game down with it.
    """

    from sidra_ai.creation.evidence import Fact
    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.intent import detect_creation_intent

    generate = build_game_generator(tmp_path)
    facts = [Fact(text="ダークは #05070f", source="tukemen-rgb/site docs/DESIGN.md")]

    outcome = generate(
        "釣りゲームを作って", detect_creation_intent("釣りゲームを作って"), facts
    )

    assert outcome.handled
    assert outcome.details["playable"]
    assert "docs/DESIGN.md" in Path(outcome.artifact_path).read_text(encoding="utf-8")


def test_no_evidence_still_cites_the_design_source(tmp_path) -> None:
    """The empty list is the ordinary case, not a degraded one."""

    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.intent import detect_creation_intent

    outcome = build_game_generator(tmp_path)(
        "釣りゲームを作って", detect_creation_intent("釣りゲームを作って"), []
    )

    assert outcome.handled
    assert "DESIGN.md" in Path(outcome.artifact_path).read_text(encoding="utf-8")
