"""The music half of §1, judged by listening to the page rather than reading it.

Every check drives the generated page in node and reads ``musicFacts`` off
the running artifact: a preamble that shipped but never ticked, a tune that
ignored the mute, or one that started humming over the briefing would all
pass a grep and fail here.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.music import probe_source


def _heard(request: str = "パズルゲームを作って") -> dict:
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


def test_every_template_carries_the_music():
    for key in TEMPLATES:
        page = generate_game("ゲームを作って", template=key).html
        assert "musicTick" in page, key


def test_quiet_until_the_first_input_then_it_plays():
    """The autoplay rule, and C-1111's: nothing hums over an untouched page."""

    facts = _heard()

    assert facts["beforeOn"] is False
    assert facts["beforeN"] == 0
    assert facts["playingN"] > 0


def test_m_stops_the_reservation():
    facts = _heard()

    assert facts["afterN"] == facts["atMuteN"]


def test_the_same_request_is_the_same_tune_and_pentatonic():
    first = _heard()
    again = _heard()
    other = _heard("シューティングゲームを作って")

    assert first["mel"] == again["mel"]
    assert first["bass"] == again["bass"]
    assert first["mel"] != other["mel"], "a different request is a different song"
    assert first["steps"] == 32, "four bars, repeated (§10 事実 2)"
    # The walk stays on the ten pentatonic degrees (or rests): the property
    # that makes an unheard generated tune safe to ship (§10 事実 3).
    assert all(-1 <= d <= 9 for d in first["mel"])
