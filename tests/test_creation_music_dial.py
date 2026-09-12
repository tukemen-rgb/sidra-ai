"""The music has a dial of its own (§30 事実 3, C-1693).

The Cognitive list at gameaccessibilityguidelines.com asks for "separate
volume controls or mutes for effects, speech and background / music"
(opened 2026-09-12; the same source §28 and §29 came from). SIDRA had one
dial: the tune and the effects rode it together and M silenced both, so
someone who wanted the music gone had to give up the effects - which are
how a player knows what just happened.

``creation_volume_axis`` had made the single dial a contract in itself
("one dial moves both, in the same ratio"), so the parent stays exactly
that and the new dial is a factor underneath it. At its default the
product sounds unchanged to the byte.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.audio import VOLUME_PROBE
from sidra_ai.creation.games import generate_game


@pytest.fixture(scope="module")
def script() -> str:
    html = generate_game("ビームで撃ち合うゲームを作って").html
    found = re.search(r"<script>(.*?)</script>", html, re.S)
    assert found is not None
    return found.group(1)


def _heard(script: str, stored: dict) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to listen")
    got = subprocess.run(
        ["node", "-"],
        input=VOLUME_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
            "STORED_INPUT", json.dumps(stored)
        ),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])


def test_the_dial_halves_the_music(script: str) -> None:
    full = _heard(script, {"volume": 100})
    half = _heard(script, {"volume": 100, "music": 50})
    assert full["tune"], "nothing was played at full"
    assert half["tune"] == pytest.approx(full["tune"] / 2, rel=1e-6)


def test_the_dial_moves_nothing_else(script: str) -> None:
    """What makes it a separate control rather than a second master."""

    full = _heard(script, {"volume": 100})
    half = _heard(script, {"volume": 100, "music": 50})
    assert full["calm"], "no effect was played at full"
    assert half["calm"] == full["calm"]


def test_zero_takes_the_tune_and_leaves_the_cues(script: str) -> None:
    """The guideline's own point: the person who silences the music keeps
    the sounds that tell them what happened."""

    full = _heard(script, {"volume": 100})
    off = _heard(script, {"volume": 100, "music": 0})
    assert off["tuneCount"] == 0, off["tuneCount"]
    assert off["calm"] == full["calm"]


def test_the_parent_dial_still_moves_both(script: str) -> None:
    """The old contract, checked from the new side: adding a child must
    not quietly take the parent's reach away."""

    full = _heard(script, {"volume": 100})
    quiet = _heard(script, {"volume": 50})
    assert quiet["calm"] == pytest.approx(full["calm"] / 2, rel=1e-6)
    assert quiet["tune"] == pytest.approx(full["tune"] / 2, rel=1e-6)


def test_the_default_changes_nothing(script: str) -> None:
    """Shipped at 100, so no page sounds different than it did."""

    from sidra_ai.creation.tuning import panel_schema

    fields = panel_schema(
        "duel",
        {"normal": (1.0, 1.0), "hard": (1.3, 1.2)},
        difficulty="normal",
        accent="#2ee6ff",
    )["fields"]
    music = [f for f in fields if f["key"] == "music"]
    assert len(music) == 1, [f["key"] for f in fields]
    assert music[0]["default"] == 100
    assert music[0]["label"] == "音楽の音量"


def test_a_page_without_a_panel_still_plays() -> None:
    """``musicGain`` is guarded by try/catch on purpose: a script assembled
    without the tuning preamble has no dial to read."""

    from sidra_ai.creation.music import MUSIC_PREAMBLE

    assert "function musicGain()" in MUSIC_PREAMBLE
    assert "catch(e){return 1}" in MUSIC_PREAMBLE
