"""A danger the player is allowed to decline.

§13 事実 1: every hazard in the product is simply to be avoided, so no
risk is ever optional. The graze band is the smallest version of Pac-Man's
blue ghosts - fly close to a hull and get paid, three brushes in a row make
a point, a hit takes the run.

The assertions are as much about restraint as about the reward: one brush
per hull, the band strictly outside a kill radius that does not move, and
points as the only reward. Anything else would make declining the risk a
mistake, which is the opposite of the point.

Driven rather than grepped, and the band is checked against the page's own
record of each brush - the hulls move inside the frame, so a gap measured
from outside is not the gap the collision judged.
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

from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402
from sidra_ai.creation.graze import (  # noqa: E402
    GRAZE_BAND,
    GRAZE_RUN,
    GRAZE_TEMPLATES,
    GRAZE_UNWIRED,
    PREAMBLE_NAMES,
    probe_source,
)

WIRED = GRAZE_TEMPLATES[0]


def _fly(mode: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to fly the round")
    found = re.search(
        r"<script>(.*?)</script>", generate_game("シューティングゲームを作って").html, re.S
    )
    assert found is not None
    run = subprocess.run(
        ["node", "-"],
        input=probe_source(found.group(1), mode=mode),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert run.returncode == 0, run.stderr.strip()[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------ the bookkeeping


def test_every_template_is_either_wired_or_has_a_reason() -> None:
    assert set(GRAZE_TEMPLATES) | set(GRAZE_UNWIRED) == set(TEMPLATES)
    assert not set(GRAZE_TEMPLATES) & set(GRAZE_UNWIRED)
    assert all(reason.strip() for reason in GRAZE_UNWIRED.values())


def test_the_preamble_reaches_only_the_wired_template() -> None:
    for name in PREAMBLE_NAMES:
        assert name in generate_game("シューティングゲームを作って").html
    assert "grazeNear" not in generate_game("キャッチゲームを作って").html


def test_the_backlog_entry_named_a_hazard_the_game_does_not_have() -> None:
    """Recorded because it is the one decision in this item.

    The entry asks for a graze band around 敵弾. The shooter has no enemy
    bullets - its hazard is the descending hull - and adding a bullet type
    would have added a hazard, which the entry's own 「難度は不変」 forbids.
    The band sits outside the hull instead.
    """

    assert "bullet" not in generate_game("シューティングゲームを作って").html.lower()


# ------------------------------------------------------------------- the risk


def test_flying_close_pays() -> None:
    hug = _fly("hug")

    assert hug["graze"]["seen"] > 0, "a hugging flight never brushed anything"
    assert hug["graze"]["paid"] > 0
    assert hug["roundScore"] > hug["score"], "the points never reach the round"


def test_it_pays_on_a_run_rather_than_per_brush() -> None:
    """One brush is luck. Three in a row is a run, which is the thing a
    hit can take away."""

    hug = _fly("hug")

    assert hug["graze"]["seen"] >= hug["graze"]["paid"] * GRAZE_RUN


def test_every_brush_happened_inside_the_band() -> None:
    """Distance earns nothing, asked of the page's own record."""

    hug = _fly("hug")
    at = hug["graze"]["at"]

    assert at, "the page recorded no brushes"
    for dist, kill in at:
        assert kill < dist <= kill + GRAZE_BAND, (dist, kill)


def test_a_hit_takes_the_run_but_not_the_bank() -> None:
    crash = _fly("crash")
    hits = [row for row in crash["timeline"] if row.get("hit")]

    assert hits, "the crashing flight never lost a hull"
    assert all(row["run"] == 0 for row in hits)


def test_crashing_is_never_a_way_to_earn() -> None:
    crash = _fly("crash")

    assert crash["hp"] == 0, "flying into hulls cost nothing"
    assert crash["graze"]["paid"] == 0


# -------------------------------------------------- what must not have moved


def test_the_kill_radius_did_not_move() -> None:
    """The band is strictly outside it, so grazing is harder than keeping
    away - never easier. Measured from the gap each hull landed from,
    because a reported radius is a number beside the check rather than the
    check itself."""

    crash = _fly("crash")
    struck = crash["graze"]["struck"]

    assert struck, "no hull landed, so the radius is unmeasured"
    assert all(dist < kill for dist, kill in struck)
    assert max(kill - dist for dist, kill in struck) <= 4


def test_the_run_is_on_screen() -> None:
    """A risk whose state the player cannot see is a gamble."""

    hug = _fly("hug")
    huds = [row["hud"] for row in hug["timeline"] if row["hud"]]

    assert huds and all("かすり" in hud for hud in huds)
