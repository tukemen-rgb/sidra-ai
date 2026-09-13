"""断り書きは、その人が使った操作子を名指す (C-1747, §4 × §8 事実 6).

C-1737 put a sentence in the panel when a colour has to be lifted to
clear this product's own accent floor. It said 「選んだ差し色」 - *the
accent you picked* - on every page, including pages where the player
picked nothing.

They can arrive at that colour another way. §8 事実 6's cosmetic unlocks
hand out three colours for a cumulative score, and **all three are under
the floor on the paper theme** (残り火 2.19:1, 霜 1.51:1, 苔むす
1.62:1), so a player wearing a reward they earned is told that the colour
*they picked* was unreadable - about a control they have never opened.

Lifting the colour is right and stays. C-1739 made the product say
things where they were asked; this is the same rule about who asked.

Both directions: the two sources are named apart, and a theme where
nothing had to move says nothing at all.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.skins import skin_spec
from sidra_ai.creation.themes import ACCENT_FLOOR, THEMES, contrast_ratio
from sidra_ai.creation.tuning import SPEED_BINDING, probe_source

TEMPLATE = "adventure"
SKIN = skin_spec(TEMPLATE)["skins"][2]


def _panel(theme: str, stored: dict) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to build the panel")
    page = generate_game("ゲームを作って", template=TEMPLATE, theme_name=theme).html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(
            found.group(1), stored=stored, speed_expr=SPEED_BINDING[TEMPLATE]
        ),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


WELL = {f"sidra.tune.{TEMPLATE}": {"accent": SKIN["accent"]}}
WORN = {
    f"sidra.total.{TEMPLATE}": str(SKIN["at"]),
    f"sidra.skin.{TEMPLATE}": SKIN["id"],
}


def test_the_unlockable_colours_really_are_under_the_floor_on_paper() -> None:
    """The measurement that makes this reachable at all."""

    ground = THEMES["paper"].tokens["surface"]
    for skin in skin_spec(TEMPLATE)["skins"][1:]:
        assert contrast_ratio(skin["accent"], ground) < ACCENT_FLOOR, skin


def test_a_picked_colour_is_named_as_picked() -> None:
    note = _panel("paper", WELL)["accentNote"]
    assert note and "選んだ差し色" in note, note
    assert "着ている色" not in note, note


def test_a_worn_colour_is_named_as_worn() -> None:
    """The defect: blaming a control the player never opened.

    The skin's own label is deliberately not quoted. Fetching it would
    have meant a fourth reach into the skin, and ``skins`` allows exactly
    three by name - a list whose whole point is that it does not grow.
    The judge caught the version that reached, which is the guard working.
    """

    seen = _panel("paper", WORN)
    note = seen["accentNote"]
    assert note, "スキンを着ているのに何も言わない"
    assert "着ている色" in note, note
    assert "選んだ差し色" not in note, note
    assert seen["accentSource"] == "skin"


@pytest.mark.parametrize("stored,kind", [(WELL, "well"), (WORN, "skin"), ({}, "theme")])
def test_a_theme_that_needs_no_lift_says_nothing(stored: dict, kind: str) -> None:
    """Without this, naming the skin every time scores full marks."""

    seen = _panel("gameyard", stored)
    assert seen["accentNote"] is None, seen["accentNote"]
    assert seen["accentSource"] == kind


def test_the_probe_can_express_what_the_page_reads_raw() -> None:
    """The tooling defect that hid this (C-1747).

    ``tuning.probe_source`` JSON-encoded every stored value, so a key the
    page reads raw - a skin id, the briefing mark - could be set and have
    no effect, and the page looked like it was ignoring the skin. It now
    matches ``together.probe_source`` and the real store: strings as
    themselves, everything else as JSON. Two probes for one page that
    disagreed about the browser cost this loop two wrong readings.
    """

    assert _panel("paper", WORN)["accentSource"] == "skin"


def test_the_panel_does_not_reach_further_into_the_skin() -> None:
    """One sanctioned call, and the sentence is built from its result."""

    from sidra_ai.creation.games import TEMPLATES
    from sidra_ai.creation.skins import stray_calls

    for template in sorted(TEMPLATES):
        page = generate_game("ゲームを作って", template=template).html
        body = re.search(r"<script>(.*?)</script>", page, re.S)
        assert body is not None
        assert stray_calls(body.group(1), template) == [], template
