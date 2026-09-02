"""Losing a round has a shape of its own.

§8 事実 2 of the play notes: being hit had juice from C-1017, but losing
the *go* felt the same as being hit. The one moment the player is asked to
decide whether to try again had no punctuation.

One shared beat - a heavier shake, a longer hold, a burst, the losing
sound - called from each template's own losing path, and from the round
clock's timeout, which is the only failure the four templates with no
losing state have.

Driven to a real failure rather than grepped. Three directions matter and
each has its own test: the beat fires on a loss, it stays silent on a win,
and under ``prefers-reduced-motion`` it keeps firing with the shake at
exactly zero - the hitstop, which withholds motion rather than adding any,
is what carries it for someone who asked for less.
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

from sidra_ai.creation.games import (  # noqa: E402
    TEMPLATES,
    _DIFFICULTY,
    generate_game,
)
from sidra_ai.creation.juice import (  # noqa: E402
    FAIL_HITSTOP,
    FAIL_PARTICLES,
    FAIL_SHAKE,
    PREAMBLE_NAMES,
)
from sidra_ai.creation.round import probe_source  # noqa: E402

KEYS = sorted(TEMPLATES)

#: Literal weights the templates pass to ``shake()``. The beat has to be
#: heavier than all of them, or it is not a beat, it is another hit.
HIT_WEIGHTS = [
    float(weight)
    for spec in TEMPLATES.values()
    for weight in re.findall(r"\bshake\(\s*([0-9.]+)\s*\)", spec.script)
]


def _lose(template: str, *, reduced: bool = False, slow: bool = True) -> dict:
    """Play until the round fails, touching nothing after the first press.

    ``slow`` stores the gentlest pace the author shipped, through the panel
    C-1113 added. It makes every template's round outlast the clock, so
    what is being watched is a *failure* rather than whichever ending
    happened to come first - racing, left alone at its normal pace, wins.
    """

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the page to a failure")
    page = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    gentle = min(pair[0] for pair in _DIFFICULTY[template].values())
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(
            script.group(1),
            reduced=reduced,
            stored={f"sidra.tune.{template}": {"speed": gentle}} if slow else None,
        ),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", KEYS)
def test_a_lost_round_gets_a_beat(template: str) -> None:
    seen = _lose(template)

    assert seen["breakAt"] is not None
    assert seen["beatsAtBreak"] == 1, "the failure produced no beat"


@pytest.mark.parametrize("template", KEYS)
def test_the_beat_moves_the_screen(template: str) -> None:
    assert _lose(template)["shakeAtBreak"] > 0


@pytest.mark.parametrize("template", KEYS)
def test_a_retry_is_offered_straight_after(template: str) -> None:
    """§8's shape is 揺れ＋粒子＋短いスロー→**即リトライ表示**.

    Read off what the page drew after the failure, not out of the source:
    a template could print the line somewhere it never reaches.
    """

    said = _lose(template)["saidAfter"]

    assert [line for line in said if "もう一度" in line or "やり直" in line], said[:6]


@pytest.mark.parametrize("template", KEYS)
def test_reduced_motion_keeps_the_beat_and_drops_the_shake(template: str) -> None:
    """Someone who asked for less movement did not ask to lose silently."""

    quiet = _lose(template, reduced=True)

    assert quiet["beatsAtBreak"] == 1
    assert quiet["shakeAtBreak"] == 0


def test_a_won_round_gets_no_beat() -> None:
    """The direction that keeps the number honest.

    Racing is the template that finishes on its own with no input at all,
    which is what makes it the case that can prove this. Counted over the
    whole run: the beat would fire on the tick *after* the ending appears,
    so reading it at the break alone would miss one.
    """

    won = _lose("racing", slow=False)

    assert won["reason"] == "template" and won["endState"] == "goal"
    assert won["beatsTotal"] == 0


# ------------------------------------------------- what the page cannot say


def test_the_beat_is_heavier_than_any_hit() -> None:
    """Otherwise it is another hit, which is the state §8 recorded."""

    assert HIT_WEIGHTS, "no literal shake weights found in any template"
    assert FAIL_SHAKE > max(HIT_WEIGHTS)
    assert FAIL_HITSTOP > 0
    assert FAIL_PARTICLES > 0


@pytest.mark.parametrize("template", KEYS)
def test_no_template_shadows_the_kit(template: str) -> None:
    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body


@pytest.mark.parametrize("template", KEYS)
def test_a_template_that_can_lose_calls_the_shared_beat(template: str) -> None:
    """The kit is shared, so a template must not grow its own version.

    A losing template that plays ``sfx('lose')`` by hand would have sound
    and nothing else - the exact half-a-beat this item replaces.
    """

    body = TEMPLATES[template].script

    assert "sfx('lose')" not in body, "losing plays the shared beat, not the sound alone"
