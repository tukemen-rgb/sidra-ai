"""C-1419: the second template where standing close is worth something.

C-1406 put a graze band just outside the shooter's kill radius. This wires
the same part to kaiju - and the entry that asked for it, like the unwired
table's own note, said 「拳」. **The boss has no fists.** It opens cracks in
the ground whose radius grows as they widen, and that is the hazard the
band went outside of. The same correction the graze module already records
for the shooter's 敵弾.

The contract from C-1406 is what these tests are mostly about, because it
is the part that is easy to break by accident: the reward is points and
nothing else, the radius that hurts does not move, and a hit takes the run.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.graze import GRAZE_BAND, GRAZE_RUN, GRAZE_TEMPLATES, GRAZE_UNWIRED
from sidra_ai.creation.kaiju import graze_probe_source
from sidra_ai.creation.round import ROUND_SCORE


def _script() -> str:
    body = re.search(
        r"<script>(.*?)</script>",
        generate_game("怪獣ゲームを作って", template="kaiju").html,
        re.S,
    )
    assert body is not None
    return body.group(1)


def _fight(**kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to fight the boss")
    probe = subprocess.run(
        ["node", "-"],
        input=graze_probe_source(_script(), **kwargs),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:500]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def hug() -> dict:
    return _fight(mode="hug", frames=3000)


@pytest.fixture(scope="module")
def crash() -> dict:
    return _fight(mode="crash", frames=3000)


# --- the table and the score ----------------------------------------------


def test_kaiju_is_wired_and_no_longer_excused() -> None:
    assert "kaiju" in GRAZE_TEMPLATES
    assert "kaiju" not in GRAZE_UNWIRED
    assert set(GRAZE_TEMPLATES) | set(GRAZE_UNWIRED) >= {"kaiju", "shooter"}


def test_the_points_are_added_to_the_count_not_folded_into_it() -> None:
    # The shooter's shape from C-1406: an expression rather than a rename,
    # so 周期 stays the count it always was on the HUD.
    expression, _ = ROUND_SCORE["kaiju"]
    assert expression == "cycles+grazeFacts().paid"


# --- standing close --------------------------------------------------------


def test_standing_beside_a_crack_pays(hug: dict) -> None:
    assert hug["graze"]["paid"] > 0
    assert hug["roundScore"] > hug["cycles"]


def test_every_brush_was_outside_the_radius_that_hurts(hug: dict) -> None:
    # Read off the page's own record of the gap it judged each brush at.
    # Measuring it from outside the frame reads the cracks before they
    # widen and reports brushes that never happened.
    assert hug["graze"]["at"]
    for dist, kill in hug["graze"]["at"]:
        assert kill < dist <= kill + GRAZE_BAND


def test_it_pays_on_a_run_not_per_brush(hug: dict) -> None:
    assert hug["graze"]["seen"] >= hug["graze"]["paid"] * GRAZE_RUN


def test_keeping_away_earns_nothing() -> None:
    assert _fight(mode="clear", frames=3000)["graze"]["paid"] == 0


# --- and what it must not change -------------------------------------------


def test_the_crack_still_costs_a_heart(crash: dict) -> None:
    assert crash["hp"] == 0
    assert crash["graze"]["struck"]


def test_every_heart_was_lost_from_inside_the_radius(crash: dict) -> None:
    for dist, kill in crash["graze"]["struck"]:
        assert dist < kill


def test_a_hit_takes_the_run(crash: dict) -> None:
    hits = [row for row in crash["timeline"] if row.get("hit")]
    assert hits
    assert all(row["run"] == 0 for row in hits)
    assert crash["graze"]["paid"] == 0


def test_reduced_motion_drops_the_particles_not_the_points() -> None:
    assert _fight(mode="hug", frames=3000, reduced=True)["graze"]["paid"] > 0
