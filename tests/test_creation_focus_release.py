"""Focus loss lets go of held keys (§22, C-1373).

A keyup released in another window never arrives (Emscripten #5122,
closed wontfix - the application's job), so the held-movement flags every
template keeps (§12 事実 3) stay pressed across alt-tab, and the hero
runs on alone. The focus preamble tracks held keys under the remap
wrapper and feeds synthetic keyups through the registered handlers on
blur / pagehide / the document going hidden.

Driven, not read: the page runs in node, a key is pressed and never
released, the focus-loss signal fires, and the game must stand still.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.focus import probe_source
from sidra_ai.creation.games import TEMPLATES


def _drive(template: str, *, hold: str, facts: str, signal: str, tweak=None) -> dict:
    html = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    src = probe_source(script, hold=hold, facts=facts, signal=signal)
    if tweak:
        src = tweak(src)
    run = subprocess.run(
        ["node", "-"], input=src, capture_output=True, text=True, timeout=180
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_every_template_carries_the_release() -> None:
    for key in sorted(TEMPLATES):
        html = generate_game("ゲームを作って", template=key).html
        assert "focusRelease" in html, f"{key} has no focus release"


@pytest.mark.parametrize(
    "template,hold,facts,signal",
    [
        ("platformer", "ArrowRight", "me.x", "blur"),
        ("shooter", "ArrowLeft", "ship.x", "hidden"),
        ("platformer", "ArrowRight", "me.x", "pagehide"),
    ],
)
def test_a_held_key_lets_go_when_the_player_leaves(
    template: str, hold: str, facts: str, signal: str
) -> None:
    got = _drive(template, hold=hold, facts=facts, signal=signal)
    assert got["moved"], "the held key never moved the game - the probe is dead"
    assert got["heldBefore"] == [hold], "the hold is not tracked"
    assert got["heldAfter"] == [], f"{signal} leaves keys held"
    assert got["drift"] == 0, (
        f"still moving after {signal}: {got['drift']:+.1f}px in 30 frames"
    )
    assert got["releases"] == 1


def test_a_remapped_held_key_releases_in_the_games_spelling() -> None:
    """Tracking sits under the remap wrapper, so 'j' held as ArrowRight
    is tracked - and released - as the key the game actually reads."""

    got = _drive(
        "platformer",
        hold="j",
        facts="me.x",
        signal="blur",
        tweak=lambda s: s.replace(
            "/* Hold the key", "remapSet('j','ArrowRight');\n/* Hold the key"
        ),
    )
    assert got["moved"], "the remapped key never moved the game"
    assert got["heldBefore"] == ["ArrowRight"], "tracked in the wrong spelling"
    assert got["heldAfter"] == [] and got["drift"] == 0


def test_a_release_with_nothing_held_is_a_no_op() -> None:
    got = _drive(
        "platformer",
        hold="ArrowRight",
        facts="me.x",
        signal="blur",
        tweak=lambda s: s.replace(
            "/* Hold the key",
            "(handlers['blur']||[]).forEach(fn=>fn({}));\n/* Hold the key",
        ),
    )
    assert got["releases"] == 1, "an empty release should not count"
