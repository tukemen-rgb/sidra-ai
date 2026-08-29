"""One press starts the game, and nothing starts without it.

The failure this replaces was invisible from the page: every template began
on load, so on a phone the instructions were below the fold and the player's
first experience was losing a life to rules they had not read. The gate is
therefore tested by running the page, not by finding a title string - a
title drawn over an already-running game would look identical in the source.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game, validate_game_html
from sidra_ai.creation.startscreen import GATE_PREAMBLE, probe_source


def _drive(template: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - node is present here
        pytest.skip("node is needed to drive the gate")
    page = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    finished = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert finished.returncode == 0, (template, finished.stderr[:400])
    return json.loads(finished.stdout)


def test_no_template_plays_a_frame_before_the_press():
    for key in TEMPLATES:
        seen = _drive(key)
        assert seen["stateBefore"] == "title", key
        assert seen["framesBeforePress"] == 0, (key, seen)


def test_one_press_starts_every_template():
    for key in TEMPLATES:
        seen = _drive(key)
        assert seen["stateAfter"] == "playing", key
        assert seen["framesAfterPress"] == 10, (key, seen)


def test_the_loop_survives_the_wait():
    # A gate that stopped re-scheduling would leave a title screen that no
    # press could ever reach, since the frame that reads the state never
    # comes. Ten frames of waiting and then ten of playing proves both.
    seen = _drive("fishing")

    assert seen["framesBeforePress"] == 0
    assert seen["framesAfterPress"] > 0


def test_the_press_that_starts_also_unlocks_the_sound():
    # Browsers refuse audio before a user gesture. If the first sfx call were
    # left to whatever the game does first, the page would be silent for the
    # players who never trigger it.
    assert "sfx('step')" in GATE_PREAMBLE
    assert "gateStart" in GATE_PREAMBLE


def test_the_title_screen_prints_the_page_s_own_instructions():
    # Not a second copy: a template whose controls change must not leave
    # stale instructions on the screen nobody can get past without reading.
    for key, spec in TEMPLATES.items():
        page = generate_game("ゲームを作って", template=key).html
        assert json.dumps(spec.how_to_play, ensure_ascii=False) in page, key


def test_the_pages_still_run_with_the_gate_in_them():
    for key in TEMPLATES:
        verdict = validate_game_html(generate_game("ゲームを作って", template=key).html)
        assert verdict["playable"], (key, verdict["failures"])


def test_the_gate_is_installed_before_the_other_preambles():
    # Wrapper order decides draw order: the first wrapper installed runs its
    # own work last, which is what puts the overlay above the pad and the
    # particles instead of under them.
    page = generate_game("ゲームを作って", template="fishing").html

    assert page.index("GATE_RAF") < page.index("JUICE_RAF") < page.index("PAD_RAF")
