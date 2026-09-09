"""The walk back saw 57% of what the walk out saw (§27, C-1622).

Scroll Back (Itay Keren, GDC 2015) names the platformer's old camera:
pure position-locking, `cam = me.x - 260` recomputed inside draw(). The
article's own verdict on it is "plenty of view space in all directions"
and no lookahead, plus a jerk on direction changes. On a 720 canvas a
hero pinned at 260 saw 460px ahead running right and 260px running left -
and this is a template whose design asks you to walk back to the lantern.

The aim now leans by CAM_LOOK toward the facing (`me.look`, which C-1348
already keeps for the eyes) from a centred anchor, and the camera lerps
toward it rather than snapping.
"""

from __future__ import annotations

import json
import re
import subprocess

from sidra_ai.creation import generate_game
from sidra_ai.creation.platformer import camera_probe

_SEEN: dict = {}


def _driven() -> dict:
    if not _SEEN:
        html = generate_game("ジャンプで進むゲームを作って").html
        script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        run = subprocess.run(
            ["node", "-"],
            input=camera_probe(script),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert run.returncode == 0, run.stderr[:400]
        _SEEN.update(json.loads(run.stdout.strip().splitlines()[-1]))
    return _SEEN


def test_the_camera_leads_the_way_the_hero_faces() -> None:
    """A centred camera with no lean would give 360 each way."""

    got = _driven()
    assert got["viewAheadRight"] >= 400, "no lead running right"
    assert got["viewAheadLeft"] >= 400, "no lead running left"


def test_both_directions_see_the_same_distance() -> None:
    """The asymmetry this fixed: 460 out, 260 back."""

    got = _driven()
    assert abs(got["viewAheadRight"] - got["viewAheadLeft"]) <= 5, (
        f"{got['viewAheadLeft']} left vs {got['viewAheadRight']} right"
    )


def test_turning_around_does_not_snap_the_world() -> None:
    """§27 事実 2: a locked camera jerks on a direction change.

    Without the lerp the lean would move the world 180px in one frame.
    """

    assert _driven()["maxJump"] <= 30


def test_the_hero_stays_on_screen() -> None:
    got = _driven()
    assert got["onScreen"]
    assert 0 < got["rightScreenX"] < got["W"]
    assert 0 < got["leftScreenX"] < got["W"]
