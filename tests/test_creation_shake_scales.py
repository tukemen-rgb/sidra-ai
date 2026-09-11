"""The same action, weighed twice (§1, C-1657).

``creation_shake_ladder`` reads Vlambeer's rule as rungs: different events
ordered against one another, the head heavier than the leg. Two pages
implement the other half of the same sentence - one event scaled by what
was put into it. The duel's kick is ``2 + charge*0.08``, so a tap fires a
thread and a long hold shoves the camera; the puzzle's is
``min(9, cells.length)``.

Neither was asked for by anything. Flattening the duel's formula to a
constant left 166 duel/juice/shake tests green, which is how this item
started.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.duel import slope_probe as duel_slope
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.puzzle import slope_probe as puzzle_slope

CASES = (
    ("ビームで撃ち合うゲームを作って", duel_slope, "charge", "duel"),
    ("パズルゲームを作って", puzzle_slope, "size", "puzzle"),
)


def _weighed(request: str, builder) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=builder(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(("request_", "builder", "field", "name"), CASES, ids=[c[3] for c in CASES])
def test_both_weights_actually_fired(request_, builder, field, name) -> None:
    """A weight that never happened is not a pass (C-1637)."""

    seen = _weighed(request_, builder)

    assert seen["light"] is not None, f"{name}: the light weight never fired"
    assert seen["heavy"] is not None, f"{name}: the heavy weight never fired"
    assert seen["light"]["kick"] > 0, name
    assert seen["heavy"]["kick"] > 0, name


@pytest.mark.parametrize(("request_", "builder", "field", "name"), CASES, ids=[c[3] for c in CASES])
def test_the_two_weights_really_were_different(request_, builder, field, name) -> None:
    """Otherwise "it scaled" would be a claim about one measurement."""

    seen = _weighed(request_, builder)

    assert seen["heavy"][field] > seen["light"][field], (name, seen)


@pytest.mark.parametrize(("request_", "builder", "field", "name"), CASES, ids=[c[3] for c in CASES])
def test_putting_more_in_kicks_harder(request_, builder, field, name) -> None:
    seen = _weighed(request_, builder)

    assert seen["heavy"]["kick"] > seen["light"]["kick"], (name, seen)


@pytest.mark.parametrize(("request_", "builder", "field", "name"), CASES, ids=[c[3] for c in CASES])
def test_each_reading_is_the_event_on_its_own(request_, builder, field, name) -> None:
    """shake() keeps its max within a frame too, so a reading taken while a
    second event was in the air belongs to whichever kicked harder."""

    seen = _weighed(request_, builder)

    for half in ("light", "heavy"):
        rang = seen[half].get("rang")
        if rang is not None:
            assert len(rang) == 1, (name, half, rang)
