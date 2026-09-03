"""The shooter, and the apology it retires.

C-1012 made "シューティングゲームを作って" say out loud that it was getting a
fishing game instead. The interesting property of that design was that it
reads support from ``TEMPLATES`` rather than a second list, so landing this
template should silence the apology with no edit to the honesty code. That
claim is worth a test of its own - it is the part a later refactor would
quietly break.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.games import (
    TEMPLATES,
    choose_template,
    detect_genre,
    generate_game,
    validate_game_html,
)
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.shooter import probe_source
from sidra_ai.creation.touchpad import unreachable_keys


def _flown(request: str = "シューティングゲームを作って") -> dict:
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
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_a_shooting_request_reaches_the_shooter():
    for text in (
        "シューティングゲームを作って",
        "弾幕ゲーム作って",
        "shooting game を作って",
    ):
        assert choose_template(text) == "shooter", text


def test_the_apology_retired_itself():
    # No edit was made to the honesty table or to game_job for this: the
    # genre was already promised, and support is read from TEMPLATES.
    genre = detect_genre("シューティングゲームを作って")

    assert genre is not None
    assert genre.template == "shooter"
    assert genre.supported is True


def test_the_summary_no_longer_says_it_could_not_build_this(tmp_path):
    generate = build_game_generator(tmp_path)
    message = "シューティングゲームを作って"

    outcome = generate(message, detect_creation_intent(message))

    assert outcome.details["genre_substituted"] is False
    assert outcome.details["built_template"] == "shooter"
    assert "まだ作れない" not in outcome.summary


def test_the_page_runs_and_carries_the_shared_preambles():
    page = generate_game("シューティングゲームを作って").html
    verdict = validate_game_html(page)

    assert verdict["playable"], verdict["failures"]
    for wired in ("sfx(", "shake(", "hitstop(", "burst(", "drawPad"):
        assert wired in page, wired


def test_difficulty_changes_the_game_and_not_the_wording():
    easy = generate_game("簡単なシューティングゲームを作って")
    hard = generate_game("難しいシューティングゲームを作って")

    assert (easy.difficulty, hard.difficulty) == ("easy", "hard")
    assert _numbers(easy.html) != _numbers(hard.html)


def _numbers(page: str) -> tuple[str, ...]:
    script = re.search(
        r"const FALL=tuneNum\('speed',([\d.]+)\),WAVE=tuneNum\('band',([\d.]+)\)", page
    )
    assert script is not None
    return script.groups()


def test_the_same_request_is_the_same_fight():
    first = generate_game("シューティングゲームを作って").html
    again = generate_game("シューティングゲームを作って").html
    other = generate_game("弾幕シューティングを作って").html

    # Spelled through the daily switch since C-1107: the request-derived
    # number is still what the page starts on, and seedNow returns it
    # unless someone turns 今日の挑戦 on.
    seed = lambda page: re.search(r"SEED=seedNow\((\d+)\)", page).group(1)  # noqa: E731
    assert seed(first) == seed(again)
    assert seed(first) != seed(other)


def test_the_round_is_three_acts_and_the_sky_steps_with_them():
    """§7 観察 5: the HUD's 第 N 波 is something the picture says too.

    Flown, not grepped: the probe pilots the fight through all three
    thirds of the round and reads the act off the running page at each.
    """

    facts = _flown()

    assert facts["state"] == "play", "the pilot reached the final act alive"
    assert facts["sceneEarly"] == 0
    assert facts["sceneMid"] == 1
    assert facts["sceneLate"] == 2


def test_the_final_act_is_the_brightest_sky_of_the_fight():
    """§7 観察 6: brightness is a budget, spent on the climax."""

    facts = _flown()
    scenes = facts["scenes"]

    assert len(scenes) == 3
    assert len({s["floor"] for s in scenes}) == 3, "each act paints its own sky"
    assert scenes[2]["lum"] > scenes[0]["lum"]
    assert scenes[2]["lum"] >= scenes[1]["lum"]


def test_the_fight_escalates_act_by_act():
    """§6 観察 3: the acts change the fight, not only the paint.

    Read off the flown page at spawn time: the final act must actually
    drop faster and spawn denser than the opening one - the docstring's
    "waves ... get faster" is a promise this test holds it to.
    """

    facts = _flown()
    spawns, vy = facts["actSpawn"], facts["actVyAvg"]

    assert facts["state"] == "play" and facts["t"] >= 3400, "reached the final act"
    assert min(spawns) >= 1, spawns
    assert vy[2] > vy[1] > vy[0], "each act falls faster than the last"
    pace_first = 1200 / spawns[0]
    pace_final = (facts["t"] - 2400) / spawns[2]
    assert pace_final < pace_first * 0.85, "the final act spawns denser"


def test_every_key_the_shooter_reads_has_a_pad_button():
    # The pad guard covers all templates, but a new one is exactly where a
    # phone-unreachable control gets added without anyone noticing.
    assert unreachable_keys(TEMPLATES["shooter"].script) == set()
