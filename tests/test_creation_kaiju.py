"""The giant-boss fight, judged by playing it rather than by reading it.

Every rule this template exists for has a cheap fake that a source check
would wave through: a big sprite instead of a withheld body, a boss that
dies to any shot instead of to the leg-then-head cycle, an attack clock
invented instead of taken from the measurement in
`docs/research/game-design-notes.md` §6. So the fight is driven in node and
the rules are read back off the running page.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.game_job import build_game_generator  # noqa: E402
from sidra_ai.creation.games import (  # noqa: E402
    TEMPLATES,
    choose_template,
    detect_genre,
    generate_game,
    validate_game_html,
)
from sidra_ai.creation.intent import detect_creation_intent  # noqa: E402
from sidra_ai.creation.kaiju import KAIJU_WORDS, probe_source  # noqa: E402

_ASK = "巨大な怪獣と戦うゲームを作って"


def _facts(request: str = _ASK) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout)


def test_the_boss_never_shows_its_body_until_it_is_beaten() -> None:
    """観察 1: hugeness is what you do not draw."""

    facts = _facts()

    assert facts["bodyWhileAlive"] is False
    assert facts["shown"] is True, "beaten, it is shown once"


def test_a_shot_that_hits_nothing_costs_the_boss_nothing() -> None:
    """Otherwise the leg phase is a delay, not a decision."""

    facts = _facts()

    assert facts["cyclesAfterMisses"] == 0
    assert facts["legHpAfterMisses"] == facts["legHpStart"]


def test_the_weak_point_opens_and_the_fight_takes_three_cycles() -> None:
    facts = _facts()

    assert facts["sawOpen"] is True
    assert facts["cycles"] == 3
    assert facts["kills"] == 3, "each cycle is one hit on the exposed head"
    assert facts["state"] == "won"


def test_the_attack_clock_is_the_measured_one() -> None:
    """§6 定量: combat cuts run 2.1s; at 60fps that is 126 frames."""

    assert _facts()["beat"] == 126


@pytest.mark.parametrize(
    "request_text",
    ["巨大な怪獣と戦うゲームを作って", "ボス戦のゲームを作って", "kaiju のゲームを作って"],
)
def test_an_ordinary_request_reaches_the_template(request_text) -> None:
    assert choose_template(request_text) == "kaiju"
    genre = detect_genre(request_text)
    assert genre is not None and genre.supported


def test_the_franchise_routes_but_never_reaches_the_artifact() -> None:
    """The genre is buildable, so the name guard is the only thing left."""

    game = generate_game("ゴジラのゲームを作って")

    assert game.template == "kaiju"
    assert "ゴジラ" not in game.html
    assert "オリジナル版" in game.tagline, "the rename says why"


def test_the_page_is_playable_and_stays_one_file() -> None:
    game = generate_game(_ASK)

    assert validate_game_html(game.html)["playable"]
    assert "assets/" not in game.html


def test_the_generator_reports_the_template_it_built(tmp_path) -> None:
    outcome = build_game_generator(tmp_path)(_ASK, detect_creation_intent(_ASK))

    assert outcome.details["built_template"] == "kaiju"
    assert outcome.details["genre_substituted"] is False
    assert outcome.details["playable"] is True


def test_every_registry_a_new_template_has_to_fill_is_filled() -> None:
    """Five tables, one template: a missing one is a silent half-landing."""

    from sidra_ai.creation.games import _DIFFICULTY
    from sidra_ai.creation.sprites import SPRITE_SETS
    from sidra_ai.creation.story import CONTROLS, PARAMETERS

    assert "kaiju" in TEMPLATES
    assert set(_DIFFICULTY["kaiju"]) == {"easy", "normal", "hard"}
    assert "kaiju" in SPRITE_SETS
    assert CONTROLS["kaiju"] and PARAMETERS["kaiju"]
    assert len(PARAMETERS["kaiju"]) == 2, "one label per difficulty number"


def test_difficulty_changes_the_fight_not_the_wording() -> None:
    from sidra_ai.creation.games import _DIFFICULTY

    easy = _DIFFICULTY["kaiju"]["easy"]
    hard = _DIFFICULTY["kaiju"]["hard"]

    assert hard[0] > easy[0], "cracks open faster"
    assert hard[1] > easy[1], "the leg takes more hits"


def test_the_words_that_route_here_include_the_ones_an_owner_types() -> None:
    for word in ("怪獣", "巨大", "ボス戦", "kaiju"):
        assert word in KAIJU_WORDS
