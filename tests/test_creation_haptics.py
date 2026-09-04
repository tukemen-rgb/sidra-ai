"""C-1413: the failure beat and a confirmed round reach the thumb too.

§16. The generated pages never called ``navigator.vibrate``, while the
devices played with a thumb are exactly the ones with a vibrator in them.
Support is Android Chrome only, so the rule this is built around is that
nothing is *told* this way - both moments keep the sound and the picture
they already had, and the buzz is a third channel on top of two.

Everything here drives a real generated page and reads the value that
reached ``navigator.vibrate``: what the page decided to ask the device
for, rather than whether a device was attached.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.juice import (
    HAPTIC_HIT,
    HAPTIC_MAX,
    HAPTIC_ROUND,
    page_probe_source,
)
from sidra_ai.creation.tuning import panel_schema


def _drive(**kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("シューティングゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=page_probe_source(script.group(1), **kwargs),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:500]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def played() -> dict:
    return _drive()


def test_the_hit_reaches_the_hand(played):
    assert played["sent"], "a failure beat asked the device for nothing"
    assert played["sent"][0] == HAPTIC_HIT


def test_a_run_of_beats_cannot_rattle_the_phone(played):
    # The window gate is the reason this is safe to ship at all, so it is
    # pushed rather than described: ten beats back to back.
    assert played["burstSteps"][-1] == HAPTIC_MAX
    assert played["max"] == HAPTIC_MAX


def test_a_played_round_confirms_itself_once(played):
    doubles = [p for p in played["sent"] if isinstance(p, list)]
    assert doubles == [list(HAPTIC_ROUND)]


def test_a_round_nobody_played_stays_silent_in_the_hand():
    # The same rule the records follow (C-1123): the keypress that opens a
    # round is not playing it.
    untouched = _drive(play=False)
    assert not [p for p in untouched["sent"] if isinstance(p, list)]
    assert not untouched["banked"]


def test_reduced_motion_silences_it():
    # A buzz is decoration by construction here, because nothing is told
    # only this way - so C-1020's rule applies without an exception.
    assert not _drive(reduced=True)["sent"]


def test_the_panel_switch_turns_it_off():
    off = _drive(stored={"sidra.tune.shooter": {"haptic": False}})
    assert off["on"] is False
    assert not off["sent"]


def test_switching_it_off_changes_nothing_else(played):
    # §16 事実 2: it may never be the only carrier. With the vibration off
    # the round still banks exactly what it banked before.
    off = _drive(stored={"sidra.tune.shooter": {"haptic": False}})
    assert off["banked"] == played["banked"]


def test_the_switch_sits_in_the_panel_beside_the_volume():
    schema = panel_schema(
        "shooter",
        {"easy": (0.5, 110), "normal": (0.8, 80), "hard": (1.25, 52)},
        difficulty="normal",
        accent="#7bdff2",
    )
    keys = [field["key"] for field in schema["fields"]]
    assert "haptic" in keys
    haptic = next(f for f in schema["fields"] if f["key"] == "haptic")
    assert haptic["type"] == "flag"
    assert haptic["default"] is True
