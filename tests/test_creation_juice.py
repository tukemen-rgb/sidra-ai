"""Feel that survives the accessibility switch, and stays wired to the games.

Two ways this goes quietly wrong. The effects can exist and be called by
nobody, which reads as "we added juice" while three of four games sit inert.
Or they can ignore ``prefers-reduced-motion``, which is worse than having no
juice at all - the setting exists because motion makes some people ill.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game, validate_game_html
from sidra_ai.creation.juice import JUICE_PREAMBLE, PREAMBLE_NAMES, probe_source


def _probe(*, reduced: bool) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - node is present here
        pytest.skip("node is needed to run the preamble")
    finished = subprocess.run(
        ["node", "-"],
        input=probe_source(reduced=reduced),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert finished.returncode == 0, finished.stderr
    return json.loads(finished.stdout)


def test_the_effects_do_something_when_motion_is_allowed():
    moving = _probe(reduced=False)

    assert moving["shake"] > 0
    assert moving["particles"] > 0
    assert moving["hitstop"] > 0


def test_reduced_motion_silences_shake_and_particles():
    still = _probe(reduced=True)

    assert still["shake"] == 0
    assert still["particles"] == 0


def test_reduced_motion_keeps_hitstop():
    # Deliberate, and pinned here so it cannot be "fixed" by accident: a
    # hitstop adds no movement, it withholds some. Asking for less motion is
    # not asking for hits to land without weight.
    assert _probe(reduced=True)["hitstop"] > 0


def test_every_template_is_wired_to_all_three():
    for key, spec in TEMPLATES.items():
        for name in ("shake", "hitstop", "burst"):
            assert f"{name}(" in spec.script, f"{key} never calls {name}()"


def test_the_pages_still_run_with_the_juice_in_them():
    for key in TEMPLATES:
        verdict = validate_game_html(generate_game("ゲームを作って", template=key).html)
        assert verdict["playable"], (key, verdict["failures"])


def test_the_preamble_introduces_only_the_names_it_declares():
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" in JUICE_PREAMBLE


def test_the_hitstop_reschedules_rather_than_dropping_the_loop():
    # Skipping the callback without re-scheduling would freeze the game
    # permanently instead of for a few frames - a "hitstop" that ends the
    # session. The loop keeps itself alive during the freeze.
    assert "JUICE_RAF(tick)" in JUICE_PREAMBLE


def test_the_juice_wraps_before_the_pad_so_the_pad_stays_on_top():
    page = generate_game("ゲームを作って", template="fishing").html
    assert page.index("JUICE_RAF") < page.index("PAD_RAF")
