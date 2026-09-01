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
