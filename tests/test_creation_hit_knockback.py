"""The hit throws the body, not just the camera (§1, C-1361).

The technique list pairs hitstop with knockback, and only the adventure's
hero had both. The kaiju soldier and the shooter ship now take an impulse
away from the impact, decaying by quarters inside half a second, clamped
by the same bounds steering respects.

The adventure's own pair was never watched here, and it was the weaker of
the two (C-1643): its shove wrote straight into hero.x while every other
mover on that page asks solid() first, so a hit taken beside a wall put
the hero inside it - and the walls there are the lock and key (§3). The
roamer's half also pointed the wrong way, shoving by -en.dx at a roamer
whose dx points AT the hero. Both are read below on a tile map, by the
page's own solid(), and in both directions: an implementation that only
stops the shove fails "away", one that only throws it fails "in a wall".
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.adventure import knock_probe
from sidra_ai.creation.kaiju import kb_probe as kaiju_probe
from sidra_ai.creation.shooter import kb_probe as shooter_probe

_CASES = {
    "kaiju": ("巨大怪獣と戦うゲームを作って", kaiju_probe, 30.0),
    "shooter": ("シューティングゲームを作って", shooter_probe, 22.0),
}


@pytest.fixture(scope="module")
def thrown() -> dict[str, dict]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    out: dict[str, dict] = {}
    for key, (request, probe, _bound) in _CASES.items():
        page = generate_game(request).html
        script = re.search(r"<script>(.*?)</script>", page, re.S)
        assert script is not None, key
        run = subprocess.run(
            ["node", "-"],
            input=probe(script.group(1)),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert run.returncode == 0, f"{key}: {run.stderr[:400]}"
        out[key] = json.loads(run.stdout.strip().splitlines()[-1])
    return out


@pytest.mark.parametrize("key", sorted(_CASES))
def test_the_hit_throws_the_body_away(thrown: dict, key: str) -> None:
    seen = thrown[key]
    assert seen["hpBefore"] - seen["hpAfter"] == 1, "one hit, one heart"
    assert seen["onHit"]["kvx"] < 0, "the impulse points away from the impact"
    assert seen["moved"] >= 12, f"the throw is a twitch ({seen['moved']:.1f}px)"


@pytest.mark.parametrize("key", sorted(_CASES))
def test_the_body_settles_and_the_wall_holds(thrown: dict, key: str) -> None:
    seen = thrown[key]
    assert seen["settledKvx"] == 0, "control never fights a phantom drift"
    bound = _CASES[key][2]
    assert seen["minX"] >= bound, "the bound holds against the throw"


# --------------------------------------------------- the dungeon's two shoves


@pytest.fixture(scope="module")
def shoved() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("冒険ゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    run = subprocess.run(
        ["node", "-"],
        input=knock_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


_SHOVES = (("roamer", "roamWall", "roamOpen"), ("guardian", "guardWall", "guardOpen"))


@pytest.mark.parametrize(("who", "wall", "open_"), _SHOVES, ids=[s[0] for s in _SHOVES])
def test_the_staged_contact_actually_lands(shoved, who, wall, open_) -> None:
    """A probe that never took a hit is not a pass (C-1637's lesson)."""

    assert shoved[wall]["hit"], f"{who}: the wall-side contact never landed"
    assert shoved[open_]["hit"], f"{who}: the open-side contact never landed"


@pytest.mark.parametrize(("who", "wall", "open_"), _SHOVES, ids=[s[0] for s in _SHOVES])
def test_the_shove_never_puts_the_hero_inside_a_wall(shoved, who, wall, open_) -> None:
    """Judged by the page's own solid(), on the hero's own footprint - the
    shrine and the optional door are solid tiles, so a shove that ignores
    them carries the hero through §3's structure."""

    assert not shoved[wall]["inWall"], f"{who}: shoved into the wall"
    assert not shoved[open_]["inWall"], f"{who}: shoved into the wall"


@pytest.mark.parametrize(("who", "wall", "open_"), _SHOVES, ids=[s[0] for s in _SHOVES])
def test_the_shove_points_away_from_whoever_landed_it(shoved, who, wall, open_) -> None:
    """The other direction, so "stop shoving entirely" cannot pass. The
    roamer chases, so its own dx points at the hero: the old -en.dx
    dragged the hero into its attacker."""

    assert shoved[open_]["away"] > 0, f"{who}: pulled toward its attacker"
    assert shoved[open_]["moved"] > 0, f"{who}: the blow moved nothing"


def test_the_contract_reads_both_of_the_dungeons_shoves() -> None:
    """C-1640's lesson: the list is what the judge walks."""

    import pathlib

    import scripts.product_metrics as _pm  # noqa: F401

    text = pathlib.Path(_pm.__file__).read_text(encoding="utf-8")
    for name in ("adventure/roamer", "adventure/guardian"):
        assert f'"{name}"' in text, name
