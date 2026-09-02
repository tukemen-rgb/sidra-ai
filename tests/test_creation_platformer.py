"""The platformer, judged by playing it rather than by reading it.

Everything that makes a jump feel right has a cheap fake a source check
would wave through: a coyote window that never closes is a double jump, a
jump cut that never fires makes the press length a label, and a "respawn"
that reloads the page is a game over wearing a kinder name. So the course is
driven in node - a late edge jump, a mid-fall jump, two falls, the lantern,
the flag - and the rules are read back off the running page.
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
from sidra_ai.creation.platformer import (  # noqa: E402
    PLATFORMER_SCRIPT,
    PLATFORMER_WORDS,
    probe_source,
)
from sidra_ai.creation.touchpad import unreachable_keys  # noqa: E402

_ASK = "横スクロールのゲームを作って"


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


def test_the_jump_rises_and_an_early_release_lowers_it() -> None:
    """Variable height: the press length is a throttle, not a label."""

    facts = _facts()

    assert facts["settledGround"] is True
    # A full hold clears real height above the ledge...
    assert facts["heldMin"] < facts["groundY"] - 40
    # ...and a tap released after three frames peaks visibly lower.
    assert facts["tapMin"] - facts["heldMin"] > 10


def test_coyote_time_is_real_and_the_window_closes() -> None:
    """A jump pressed just after the ledge lands; ten frames later it dies.

    Both halves matter: without the first the edge eats inputs, and without
    the second the game has a quiet double jump.
    """

    facts = _facts()

    assert 5 <= facts["window"] <= 7
    assert facts["leftGround"] is True
    assert facts["coyoteJump"] is True, "two airborne frames is inside the window"
    assert facts["lateJumpRefused"] is True, "ten airborne frames is past it"


def test_falling_costs_a_walk_back_and_never_the_run() -> None:
    facts = _facts()

    assert facts["firstRespawnX"] == 60, "the first fall goes back to the start"
    assert facts["firstRespawnState"] == "play", "no game over on a missed jump"
    assert facts["secondRespawn"] is True


def test_gems_count_and_the_lantern_is_their_sink() -> None:
    """§5: a tap with an outlet. Five gems light the lantern, the gems
    leave, and the respawn point moves to it."""

    facts = _facts()

    assert facts["gemsAfterOrb"] == facts["gemsBefore"] + 1
    assert facts["lampLit"] is True
    assert facts["gemsAfterLamp"] == 0, "lighting the lantern spends the gems"
    assert facts["thirdRespawnX"] == facts["lampX"], "the fall after it returns there"


def test_the_flag_ends_the_run_in_a_completed_state() -> None:
    assert _facts()["state"] == "goal"


def test_the_course_walks_through_three_palettes_toward_the_brightest() -> None:
    """§7 観察 5-6: progress picks the hue; the goal stretch is the peak."""

    scenes = _facts()["scenes"]

    assert len(scenes) == 3
    assert len({s["floor"] for s in scenes}) == 3
    brightest = max(range(len(scenes)), key=lambda i: scenes[i]["lum"])
    assert brightest == len(scenes) - 1, [round(s["lum"], 4) for s in scenes]


def test_a_template_with_no_fight_never_claims_one() -> None:
    """The loudness step is for fights, and this template has none."""

    assert "combat(" not in PLATFORMER_SCRIPT
    assert _facts()["combatOn"] is False


def test_every_control_has_a_touch_button() -> None:
    page = generate_game(_ASK).html

    assert "drawPad" in page
    assert unreachable_keys(PLATFORMER_SCRIPT) == set()


@pytest.mark.parametrize(
    "request_text",
    ["プラットフォーマーを作って", "横スクロールのゲームを作って", "platformer game を作って"],
)
def test_an_ordinary_request_reaches_the_template(request_text) -> None:
    assert choose_template(request_text) == "platformer"
    genre = detect_genre(request_text)
    assert genre is not None and genre.supported


def test_a_scrolling_shooter_is_still_a_shooter() -> None:
    """「横スクロール」 is a modifier as often as a genre; the router and the
    honesty table have to agree on which word wins the sentence."""

    request = "横スクロールシューティングを作って"

    assert choose_template(request) == "shooter"
    genre = detect_genre(request)
    assert genre is not None and genre.template == "shooter"


def test_the_page_is_playable_and_stays_one_file() -> None:
    game = generate_game(_ASK)

    assert game.template == "platformer"
    verdict = validate_game_html(game.html)
    assert verdict["playable"], verdict["failures"]
    assert "assets/" not in game.html


def test_the_generator_reports_the_template_it_built(tmp_path) -> None:
    outcome = build_game_generator(tmp_path)(_ASK, detect_creation_intent(_ASK))

    assert outcome.details["built_template"] == "platformer"
    assert outcome.details["genre_substituted"] is False
    assert outcome.details["playable"] is True


def test_every_registry_a_new_template_has_to_fill_is_filled() -> None:
    """Six tables, one template: a missing one is a silent half-landing."""

    from sidra_ai.creation.games import _DIFFICULTY
    from sidra_ai.creation.sprites import SPRITE_SETS
    from sidra_ai.creation.startscreen import BRIEFINGS
    from sidra_ai.creation.story import CONTROLS, PARAMETERS

    assert "platformer" in TEMPLATES
    assert set(_DIFFICULTY["platformer"]) == {"easy", "normal", "hard"}
    assert "platformer" in SPRITE_SETS
    assert CONTROLS["platformer"] and PARAMETERS["platformer"]
    assert len(PARAMETERS["platformer"]) == 2, "one label per difficulty number"
    assert len(BRIEFINGS["platformer"]) == 3


def test_difficulty_changes_the_course_not_the_wording() -> None:
    from sidra_ai.creation.games import _DIFFICULTY

    easy = _DIFFICULTY["platformer"]["easy"]
    hard = _DIFFICULTY["platformer"]["hard"]

    assert hard[0] > easy[0], "the gaps grow"
    assert hard[1] > easy[1], "the course gets longer"


def test_the_course_is_seeded_by_the_request() -> None:
    same_a = generate_game("横スクロールのゲームを作って")
    same_b = generate_game("横スクロールのゲームを作って")
    other = generate_game("難しい横スクロールのゲームを作って")

    assert same_a.html == same_b.html
    assert same_a.html != other.html
    assert "SEED_TOKEN" not in same_a.html


def test_the_words_that_route_here_include_the_ones_an_owner_types() -> None:
    for word in ("プラットフォーマー", "横スクロール", "platformer"):
        assert word in PLATFORMER_WORDS
