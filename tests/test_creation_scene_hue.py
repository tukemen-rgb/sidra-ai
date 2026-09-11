"""Hue is what names the place (§7 観察 5, C-1690).

The observation, in its own words: 土台は全編ほぼ同じ暗い無彩色で、場所
ごとにアクセント 1 系統だけを載せ替えている……**色相を見れば場所が
分かる**＝色が場面のラベルとして機能している.

``creation_scene_palettes`` drives ten templates across four themes and
proves two things about the difference between scenes: the three floors
are three different strings, and the brightest scene is last. Three
lightness steps of a single hue satisfy both - and destroy the thing the
observation is about. Nothing read the hue.

Measured across the forty cells: the scenes sit 26.2°-60.0° apart, and
the floor's saturation never passes 0.58. The product was right; the
design that made it right had nothing holding it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game

APART = 20.0
GROUND = 0.70

HARNESS = """
const nothing = new Proxy(function(){}, {
  get: (t,k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (t, f) => { (handlers[t] = handlers[t] || []).push(f) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({ width:720, height:320, style:{},
  addEventListener(){}, getBoundingClientRect: () => ({left:0,top:0,width:720,height:320}),
  getContext: () => nothing }), addEventListener(){} };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.requestAnimationFrame = () => 1;
SCRIPT_PLACEHOLDER
console.log(JSON.stringify(sceneFacts()));
"""

CELLS = [
    ("adventure", "迷宮を冒険するゲームを作って", ""),
    ("adventure/paper", "迷宮を冒険するゲームを作って", "紙のテーマで"),
    ("kaiju", "巨大怪獣と戦うゲームを作って", ""),
    ("racing", "レースゲームを作って", "dusk のテーマで"),
    ("catch", "落ちものをキャッチするゲームを作って", ""),
]


def _hsl(colour: str) -> tuple[float, float, float]:
    raw = colour.lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    red, green, blue = (int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))
    high, low = max(red, green, blue), min(red, green, blue)
    light = (high + low) / 2
    span = high - low
    if span == 0:
        return 0.0, 0.0, light
    sat = span / (2 - high - low) if light > 0.5 else span / (high + low)
    if high == red:
        hue = ((green - blue) / span) % 6
    elif high == green:
        hue = (blue - red) / span + 2
    else:
        hue = (red - green) / span + 4
    return hue * 60, sat, light


def _apart(one: float, two: float) -> float:
    gap = abs(one - two) % 360
    return min(gap, 360 - gap)


@pytest.fixture(scope="module")
def floors() -> dict[str, list[str]]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to paint the scenes")
    out: dict[str, list[str]] = {}
    for label, request, suffix in CELLS:
        html = generate_game(f"{request} {suffix}".strip()).html
        found = re.search(r"<script>(.*?)</script>", html, re.S)
        assert found is not None
        got = subprocess.run(
            ["node", "-"],
            input=HARNESS.replace("SCRIPT_PLACEHOLDER", found.group(1)),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert got.returncode == 0, got.stderr[:400]
        scenes = json.loads(got.stdout.strip().splitlines()[-1])["scenes"]
        out[label] = [s["floor"] for s in scenes]
    return out


def test_every_scene_pair_is_apart_in_hue(floors: dict[str, list[str]]) -> None:
    """The defect a lightness-only palette would slip past."""

    for label, painted in floors.items():
        assert len(painted) >= 3, (label, painted)
        hues = [_hsl(colour)[0] for colour in painted]
        pairs = [
            (_apart(hues[i], hues[j]), i, j)
            for i in range(len(hues))
            for j in range(i + 1, len(hues))
        ]
        nearest = min(pairs)
        assert nearest[0] >= APART, (label, nearest, painted)


def test_the_ground_stays_a_ground(floors: dict[str, list[str]]) -> None:
    """One accent swapped in, not a world repainted."""

    for label, painted in floors.items():
        loudest = max(_hsl(colour)[1] for colour in painted)
        assert loudest <= GROUND, (label, loudest, painted)


def test_different_strings_are_not_the_same_as_different_hues() -> None:
    """Why the existing contract could not have caught this: three
    lightness steps of one hue are three different strings."""

    faked = ["#101820", "#1d2d3c", "#2a4258"]
    assert len(set(faked)) == 3
    hues = [_hsl(colour)[0] for colour in faked]
    nearest = min(
        _apart(hues[i], hues[j])
        for i in range(len(hues))
        for j in range(i + 1, len(hues))
    )
    assert nearest < APART, nearest
