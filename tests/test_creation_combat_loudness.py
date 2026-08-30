"""The fight is louder than the walking around, and never louder than M.

§6 観察 4: the owner's episode does not only play different sounds when the
fighting starts, it plays them louder - its combat windows sit at
-13.8..-16.5 LUFS, clear of the dialogue scenes.

A volume step has three failure modes that a source check cannot see: it is
declared and never reaches the gain, it overrides the operator's mute, or it
lets a fight clip. A fourth is worse - `combat(true)` behind a condition that
is never true - so the templates are played and asked.
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

from sidra_ai.creation.audio import (  # noqa: E402
    COMBAT_GAIN,
    MAX_GAIN,
    probe_source,
)
from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402

#: Templates whose play state is a fight. The adventure raises the step only
#: while an enemy is near - the better design, and one this stub cannot drive
#: far enough to observe, so it is not asserted here either.
FIGHTS = {"duel", "kaiju", "shooter"}
QUIET = {"fishing", "catch", "puzzle"}


def _sound(template: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to record the page's gains")
    page = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout)


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_combat_is_louder_and_comes_back_down(template) -> None:
    seen = _sound(template)

    assert seen["hasCombat"] is True
    assert seen["loud"] > seen["calm"]
    assert seen["loud"] == pytest.approx(min(MAX_GAIN, seen["calm"] * COMBAT_GAIN))
    assert seen["backToCalm"] == seen["calm"], "a step that stays is not a step"


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_mute_still_wins_during_a_fight(template) -> None:
    """A volume feature that can override the operator's mute is a bug."""

    assert _sound(template)["mutedPlayed"] == 0


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_no_fight_can_clip(template) -> None:
    """A game whose fights clip is not louder, it is broken."""

    assert _sound(template)["peak"] <= MAX_GAIN + 1e-9


@pytest.mark.parametrize("template", sorted(FIGHTS))
def test_a_template_with_a_fight_raises_the_step_by_itself(template) -> None:
    assert _sound(template)["combatDuringPlay"] is True


@pytest.mark.parametrize("template", sorted(QUIET))
def test_a_template_without_a_fight_does_not_claim_one(template) -> None:
    assert _sound(template)["combatDuringPlay"] is False


def test_the_step_is_a_number_the_tests_can_read() -> None:
    """Both constants live in Python so the page cannot drift from them."""

    page = generate_game("ゲームを作って", template="kaiju").html

    assert f"COMBAT_GAIN={COMBAT_GAIN}" in page
    assert f"MAX_GAIN={MAX_GAIN}" in page
    assert "COMBAT_GAIN_TOKEN" not in page, "the token was substituted"
