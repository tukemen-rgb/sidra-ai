"""Control re-assignment (§4's fifth basic), judged by steering the page.

The probe drives the real puzzle template: an unassigned key must do
nothing, the same key must move the cursor once assigned to a control the
game reads, the canonical key must keep working, and the assignment must
land in this-device storage only.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.remap import preamble_for, probe_source
from sidra_ai.creation.touchpad import keys_read


def _held() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("パズルゲームを作って").html
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


def test_every_template_carries_the_remap():
    for key in TEMPLATES:
        page = generate_game("ゲームを作って", template=key).html
        assert "remapSet" in page, key


def test_an_unassigned_key_is_nobodys_control():
    held = _held()

    assert held["afterRaw"] == held["start"]


def test_an_assigned_key_steers_the_game_and_the_original_survives():
    held = _held()

    assert held["accepted"] is True
    assert held["afterMapped"] == held["afterRaw"] + 1, "j now steers right"
    assert held["afterCanon"] == held["afterMapped"] + 1, "ArrowRight still does"


def test_only_keys_the_game_reads_are_offered_or_accepted():
    held = _held()

    assert held["refused"] is False, "a control the game lacks is rejected"
    assert set(held["actions"]) == keys_read(TEMPLATES["puzzle"].script)


def test_the_assignment_stays_on_this_device():
    held = _held()

    assert held["stored"] is not None
    assert json.loads(held["stored"]) == {"j": "ArrowRight"}


def test_the_form_offers_exactly_what_each_template_reads():
    # Build-time property, template by template: the actions token is the
    # parser's own answer, so the form can never offer a missing control.
    for key, spec in TEMPLATES.items():
        preamble = preamble_for(key, spec.script)
        actions = re.search(r"REMAP_ACTIONS=(\[[^\]]*\])", preamble)
        assert actions is not None, key
        assert set(json.loads(actions.group(1))) == keys_read(spec.script), key
