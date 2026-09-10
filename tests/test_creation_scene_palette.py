"""A room you can tell from the last room, and a climax you can see coming.

§7 観察 5-6 of the owner's viewing notes, from the machine-extracted colour
script of the episode: scenes are separated by one accent hue over a shared
neutral base, and the brightest frame of the whole episode is spent on the
climax rather than handed out per scene.

Everything here is read off the running page. A palette table that exists and
a page that paints with it are different facts, and only the second is worth
asserting - the same distinction that made C-1018's pond ship as dead code.

Three properties, and the third is the one that keeps this honest: a scene
palette is decoration, so it may not spend the wall/floor value gap that
§4 makes terrain readable by.
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

from sidra_ai.creation.adventure import world_probe  # noqa: E402
from sidra_ai.creation.games import generate_game  # noqa: E402
from sidra_ai.creation.kaiju import probe_source  # noqa: E402
from sidra_ai.creation.adventure import scene_order_probe  # noqa: E402
from sidra_ai.creation.catchgame import probe_source as catch_probe  # noqa: E402
from sidra_ai.creation.duel import pace_probe as duel_probe  # noqa: E402
from sidra_ai.creation.fishing import probe_source as fishing_probe  # noqa: E402
from sidra_ai.creation.marble import probe_source as marble_probe  # noqa: E402
from sidra_ai.creation.platformer import probe_source as plat_probe  # noqa: E402
from sidra_ai.creation.puzzle import sky_probe as puzzle_probe  # noqa: E402
from sidra_ai.creation.shooter import probe_source as shooter_probe  # noqa: E402
from sidra_ai.creation.racing import probe_source as racing_probe  # noqa: E402
from sidra_ai.creation.scene import (  # noqa: E402
    ADVENTURE_PALETTE,
    KAIJU_PALETTE,
)
from sidra_ai.creation.themes import THEMES, select_theme  # noqa: E402

#: (request, probe builder, expected scene count). Only the two templates
#: that have more than one scene: a single-scene template has nothing to
#: tell apart, and counting it would inflate the number.
TARGETS = (
    ("迷宮を冒険するゲームを作って", world_probe, len(ADVENTURE_PALETTE)),
    ("巨大怪獣と戦うゲームを作って", probe_source, len(KAIJU_PALETTE)),
)

#: The default plus every named theme, because a scene palette that replaced
#: the theme instead of shifting it would pass on the default alone.
SUFFIXES = ("", "紙のテーマで", "ターミナルのテーマで", "dusk のテーマで")

CASES = [
    pytest.param(request, builder, count, suffix, id=f"{request[:4]}-{suffix or 'default'}")
    for request, builder, count in TARGETS
    for suffix in SUFFIXES
]


def _luminance(hexcolour: str) -> float:
    raw = hexcolour.lstrip("#")
    parts = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _scenes(request: str, builder, suffix: str) -> list[dict]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to read the page's own colours")
    page = generate_game(f"{request} {suffix}".strip()).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=builder(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    seen = json.loads(probe.stdout.strip().splitlines()[-1])
    return seen["scenes"]


def _acts(request: str, builder, suffix: str) -> list[int]:
    """Which acts the page actually went through, in order (C-1640)."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to read the page's own colours")
    page = generate_game(f"{request} {suffix}".strip()).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=builder(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])["sceneOrder"]


@pytest.mark.parametrize(("request_", "builder", "count", "suffix"), CASES)
def test_every_scene_paints_its_own_floor(request_, builder, count, suffix) -> None:
    scenes = _scenes(request_, builder, suffix)

    assert len(scenes) == count
    floors = [s["floor"] for s in scenes]
    assert len(set(floors)) == count, f"scenes share a floor colour: {floors}"


@pytest.mark.parametrize(("request_", "builder", "count", "suffix"), CASES)
def test_the_brightest_scene_is_the_last_one(request_, builder, count, suffix) -> None:
    """The peak is a budget spent once, at the climax - not per scene."""

    scenes = _scenes(request_, builder, suffix)
    brightest = max(range(len(scenes)), key=lambda i: scenes[i]["lum"])

    assert brightest == len(scenes) - 1, [round(s["lum"], 4) for s in scenes]


@pytest.mark.parametrize(("request_", "builder", "count", "suffix"), CASES)
def test_the_wall_keeps_its_value_gap(request_, builder, count, suffix) -> None:
    """Decoration may not spend the contrast that makes terrain readable.

    The gap is compared against the *untinted* theme rather than an absolute
    floor: the claim is that a scene palette costs nothing, and an absolute
    threshold would have quietly allowed a page to lose most of it.
    """

    scenes = _scenes(request_, builder, suffix)
    tokens = select_theme(f"{request_} {suffix}".strip()).tokens
    untinted = _ratio(_luminance(tokens["surface"]), _luminance(tokens["border"]))

    worst = min(_ratio(s["lum"], s["wallLum"]) for s in scenes)
    assert worst >= untinted - 0.02, f"{worst:.3f} against an untinted {untinted:.3f}"


def test_naming_no_theme_still_changes_nothing() -> None:
    """The scene palette shifts the theme; it does not become the theme."""

    default = _scenes("迷宮を冒険するゲームを作って", world_probe, "")
    paper = _scenes("迷宮を冒険するゲームを作って", world_probe, "紙のテーマで")

    assert [s["floor"] for s in default] != [s["floor"] for s in paper]


def test_the_palettes_are_declared_per_template() -> None:
    """Two scenes with the same entry would be one scene wearing two names."""

    for palette in (ADVENTURE_PALETTE, KAIJU_PALETTE):
        assert len(set(palette)) == len(palette)
        assert palette[-1][2] == max(entry[2] for entry in palette), (
            "the climax has to hold the largest share of the brightness budget"
        )


def test_every_theme_is_covered_by_these_cases() -> None:
    """A theme added without a case here would go unmeasured."""

    covered = {select_theme(f"ゲームを作って {suffix}".strip()).key for suffix in SUFFIXES}

    assert covered == set(THEMES)


# ------------------------------------------- the two that were left off the list


#: Both have painted a scene per act since C-1036 / C-1354 - racing per lap,
#: the platformer per third of the course - and both probes already reported
#: `scenes` in the shape the contract reads. What was missing was the name on
#: the list (C-1640), which is the shape C-1620 found for the marble.
LATE = (
    ("レースゲームを作って", racing_probe),
    ("ジャンプで進むゲームを作って", plat_probe),
)

LATE_CASES = [
    pytest.param(request, builder, suffix, id=f"{request[:4]}-{suffix or 'default'}")
    for request, builder in LATE
    for suffix in SUFFIXES
]


@pytest.mark.parametrize("request_,builder,suffix", LATE_CASES)
def test_the_late_two_paint_a_scene_per_act(request_, builder, suffix) -> None:
    scenes = _scenes(request_, builder, suffix)

    assert len(scenes) == 3
    assert len({scene["floor"] for scene in scenes}) == 3


@pytest.mark.parametrize("request_,builder,suffix", LATE_CASES)
def test_the_late_two_keep_the_brightest_for_last(request_, builder, suffix) -> None:
    scenes = _scenes(request_, builder, suffix)
    peak = max(range(len(scenes)), key=lambda i: scenes[i]["lum"])

    assert peak == len(scenes) - 1


@pytest.mark.parametrize("request_,builder,suffix", LATE_CASES)
def test_the_late_two_keep_the_wall_apart_from_the_floor(request_, builder, suffix) -> None:
    """The palette carries mood; the terrain is still shape and value."""

    scenes = _scenes(request_, builder, suffix)
    worst = min(_ratio(scene["lum"], scene["wallLum"]) for scene in scenes)

    assert worst >= 1.2, worst


def test_the_contract_names_every_template_that_has_scenes() -> None:
    """C-1640: the list is what the judge walks, so a template that paints
    scenes and is not on it is a property nothing watches."""

    import pathlib

    import scripts.product_metrics as _pm  # noqa: F401

    text = pathlib.Path(_pm.__file__).read_text(encoding="utf-8")
    block = text[text.index("_scene_targets = ("):]
    block = block[: block.index("\n    )")]

    for name in ("racing", "platformer", "marble", "puzzle", "duel"):
        assert f'"{name}"' in block, name


@pytest.mark.parametrize("request_,builder,suffix", LATE_CASES)
def test_the_late_two_go_through_their_acts_in_order(request_, builder, suffix) -> None:
    """The palette table is not the performance (C-1640). Pinning
    ``setScene(0)`` for the whole run leaves three distinct colours in the
    table, the brightest still last, and every other check here passing -
    which is exactly what the destruction found.
    """

    assert _acts(request_, builder, suffix) == [0, 1, 2]


# ------------------------------------------- every template, as the acts happened


#: All ten, each driven by the probe the contract itself uses (C-1645).
#: The palette table is not the performance: C-1640 showed a page pinned to
#: act 0 passing a contract that read only the table, and closed that for
#: two of the ten. These are the other eight.
ACT_CASES = (
    ("迷宮を冒険するゲームを作って", scene_order_probe),
    ("巨大怪獣と戦うゲームを作って", probe_source),
    ("シューティングゲームを作って", shooter_probe),
    ("玉転がしゲームを作って", marble_probe),
    ("釣りゲームを作って", fishing_probe),
    ("キャッチゲームを作って", catch_probe),
    ("ビームで撃ち合うゲームを作って", duel_probe),
    ("パズルゲームを作って", puzzle_probe),
    ("レースゲームを作って", racing_probe),
    ("ジャンプで進むゲームを作って", plat_probe),
)


@pytest.mark.parametrize(
    ("request_", "builder"), ACT_CASES, ids=[c[0][:6] for c in ACT_CASES]
)
def test_every_template_paints_every_one_of_its_acts(request_, builder) -> None:
    """§7 観察 5: the hue is the label for the place, which means every
    place has to actually get painted."""

    order = _acts(request_, builder, "")

    assert set(order) == {0, 1, 2}, order


@pytest.mark.parametrize(
    ("request_", "builder"), ACT_CASES, ids=[c[0][:6] for c in ACT_CASES]
)
def test_every_template_saves_the_brightest_act_for_last(request_, builder) -> None:
    """§7 観察 6: brightness is a resource kept back for the climax. Not
    "the order is exactly [0,1,2]" - the kaiju paints [0,1,0,1,0,1,2]
    because the boss cycles leg/open until it goes down (§6 観察 3), and
    that is the escalation working. What must hold is that the brightest
    act is entered once, at the end."""

    order = _acts(request_, builder, "")

    assert order.index(2) == len(order) - 1, order
