"""The race, judged by driving it rather than by reading it.

Each rule the template exists for has a cheap fake a source check would wave
through: a scroller with a car drawn on it (steering that moves nothing), an
obstacle field that is scenery (contact that costs nothing), a lap counter
that is a label (a finish that never arrives), and a combat-loudness step
claimed by a game with no combat. So the race is driven in node and the
rules are read back off the running page.
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
from sidra_ai.creation.racing import RACING_WORDS, probe_source  # noqa: E402

_ASK = "レースゲームを作って"


def _facts(request: str = _ASK) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
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


def test_the_page_starts_behind_the_briefing_and_then_races() -> None:
    """The gate is pressed by the probe; what it hands over is a race."""

    facts = _facts()

    assert facts["stateStart"] == "race"


def test_steering_moves_the_car_both_ways() -> None:
    facts = _facts()

    assert facts["leftMoved"] < -30
    assert facts["rightMoved"] > 30


def test_an_obstacle_costs_speed_and_not_the_run() -> None:
    """即死にしない: contact is a time penalty read off the pace itself."""

    facts = _facts()

    assert facts["spdAfterHit"] < facts["base"] * 0.55
    assert facts["graceAfterHit"] > 0, "the hit registered"
    # The run went on to finish, so the cost was speed, not the race.
    assert facts["state"] == "goal"


def test_three_laps_then_the_goal_with_a_time_per_lap() -> None:
    facts = _facts()

    assert facts["laps"] == 3
    assert facts["lapCrossings"] == 2, "lap 1→2 and 2→3; the third crossing is the goal"
    assert facts["state"] == "goal"
    assert facts["lapTimes"] == 3, "one recorded time per lap"


def test_the_final_lap_is_the_brightest_frame_of_the_run() -> None:
    """§7 観察 6, at lap scale: brightness is spent on the climax."""

    scenes = _facts()["scenes"]

    assert len(scenes) == 3
    assert scenes[2]["lum"] > scenes[0]["lum"]
    assert scenes[2]["lum"] >= scenes[1]["lum"]


def test_a_game_with_no_combat_does_not_claim_the_combat_step() -> None:
    """§6 観察 4 is for fights. A race that called combat(true) would be
    borrowing loudness for a battle it does not have - the same shape of
    dishonesty as calling a fishing game a shooter."""

    assert "combat(" not in TEMPLATES["racing"].script


def test_the_touch_pad_reaches_every_control_the_race_reads() -> None:
    from sidra_ai.creation.touchpad import unreachable_keys

    page = generate_game(_ASK).html

    assert "drawPad" in page
    assert unreachable_keys(TEMPLATES["racing"].script) == set()


@pytest.mark.parametrize(
    "request_text",
    ["レースゲームを作って", "レーシングゲームを作って", "サーキットのゲームを作って"],
)
def test_an_ordinary_request_reaches_the_template(request_text) -> None:
    assert choose_template(request_text) == "racing"
    genre = detect_genre(request_text)
    assert genre is not None and genre.supported


def test_the_page_is_playable_and_stays_one_file() -> None:
    game = generate_game(_ASK)

    assert validate_game_html(game.html)["playable"]
    assert "assets/" not in game.html


def test_the_generator_reports_the_template_without_an_apology(tmp_path) -> None:
    """The genre table promised レース; landing the template retires the
    caveat, and a caveat on a request we did satisfy is its own dishonesty."""

    outcome = build_game_generator(tmp_path)(_ASK, detect_creation_intent(_ASK))

    assert outcome.details["built_template"] == "racing"
    assert outcome.details["genre_substituted"] is False
    assert outcome.details["playable"] is True
    assert "まだ作れない" not in outcome.summary


def test_every_registry_a_new_template_has_to_fill_is_filled() -> None:
    """Five tables, one template: a missing one is a silent half-landing."""

    from sidra_ai.creation.games import _DIFFICULTY
    from sidra_ai.creation.sprites import SPRITE_SETS
    from sidra_ai.creation.startscreen import BRIEFINGS
    from sidra_ai.creation.story import CONTROLS, PARAMETERS

    assert "racing" in TEMPLATES
    assert set(_DIFFICULTY["racing"]) == {"easy", "normal", "hard"}
    assert "racing" in SPRITE_SETS
    assert "racing" in BRIEFINGS and len(BRIEFINGS["racing"]) == 3
    assert CONTROLS["racing"] and PARAMETERS["racing"]
    assert len(PARAMETERS["racing"]) == 2, "one label per difficulty number"


def test_difficulty_changes_the_race_not_the_wording() -> None:
    from sidra_ai.creation.games import _DIFFICULTY

    easy = _DIFFICULTY["racing"]["easy"]
    hard = _DIFFICULTY["racing"]["hard"]

    assert hard[0] > easy[0], "more road per second"
    assert hard[1] < easy[1], "and less of it empty"


def test_the_words_that_route_here_include_the_ones_an_owner_types() -> None:
    for word in ("レース", "レーシング", "racing", "サーキット"):
        assert word in RACING_WORDS
