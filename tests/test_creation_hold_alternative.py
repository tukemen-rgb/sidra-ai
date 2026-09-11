"""A button held down is never the only way (§29, C-1662).

GAG's motor guidelines ask, at intermediate level, that holding a button
be avoided or given an alternative. §4 has carried the visual rule since
the beginning - do not convey by colour alone - and §28 the auditory one.
This is the third of the same shape, and the duel was the wall: keydown to
hold, keyup to fire, and ``charge > 18`` before anything leaves the
barrel, so a short tap fired nothing and there was no second path.

The panel's fourth channel (after volume, haptics and motion) turns the
same one button into press-to-charge and press-again-to-fire. Off by
default, because the hold is the authored feel.

Both directions are checked here. Only one of them would pass a page that
latched always, or one that latched never.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.duel import latch_probe
from sidra_ai.creation.games import generate_game


def _tapped(latch: bool) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("ビームで撃ち合うゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=latch_probe(script.group(1), latch=latch),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_by_default_a_tap_still_fires_nothing() -> None:
    """The hold is the authored feel; the switch must not quietly remove it."""

    seen = _tapped(False)

    assert seen["latch"] is False
    assert not seen["fired"], seen
    assert seen["charge"] == 0, seen


def test_with_the_switch_on_taps_alone_put_a_beam_out() -> None:
    seen = _tapped(True)

    assert seen["latch"] is True
    assert seen["heldAfterFirstTap"], "the first tap did not start the charge"
    assert seen["fired"], seen


def test_the_tapped_charge_clears_the_barrel() -> None:
    """`fire()` drops anything at or below 18, so "a beam came out" has to
    mean a real one, not a click."""

    seen = _tapped(True)

    assert seen["charge"] > 18, seen


def test_the_panel_carries_the_switch() -> None:
    """Read off the page the player actually gets, not the schema helper:
    the switch is only real if it reaches the generated panel."""

    page = generate_game("ビームで撃ち合うゲームを作って").html
    spec = re.search(r"const TUNE_SPEC=(\{.*?\});", page, re.S)
    assert spec is not None
    fields = json.loads(spec.group(1))["fields"]
    latch = [f for f in fields if f["key"] == "latch"]

    assert latch, [f["key"] for f in fields]
    assert latch[0]["type"] == "flag"
    assert latch[0]["default"] is False, "the authored hold stays the default"
