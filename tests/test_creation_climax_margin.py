"""The climax keeps a margin (§7 観察 6, C-1703).

The observation's verb is 取っておく - brightness is a resource held back,
which is why the opening and the talk scenes are kept deliberately dark
and the monster's stand-off is the brightest palette in the film.

``creation_scene_palettes`` holds the *order* (the brightest act is last)
and C-1690 added that the scenes differ in *hue*. Neither asks by how
much. Shrink the budget to 0.001 and "brightest last" is still true while
the peak stops being a peak.

A second direction was tried and the product disproved it: "the climax's
step is the largest step in the run" fails on the paper theme, where
``scene.py`` spends the budget mirrored, and on adventure, whose middle
act is deliberately the darkest (§7 観察 8's long quiet valley). The
design is "the peak stands above every other scene", so that is what is
held here.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game

MARGIN = 1.08

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
    ("racing/dusk", "レースゲームを作って", "dusk のテーマで"),
]


def _ratio(one: float, two: float) -> float:
    high, low = max(one, two), min(one, two)
    return (high + 0.05) / (low + 0.05)


@pytest.fixture(scope="module")
def lums() -> dict[str, list[float]]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to paint the scenes")
    out: dict[str, list[float]] = {}
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
        out[label] = [s["lum"] for s in scenes]
    return out


def test_the_last_act_is_the_brightest(lums: dict[str, list[float]]) -> None:
    for label, values in lums.items():
        assert len(values) >= 3, (label, values)
        assert values[-1] >= max(values[:-1]), (label, values)


def test_the_climax_stands_apart(lums: dict[str, list[float]]) -> None:
    """The defect an order cannot see: a peak that wins by a hair."""

    for label, values in lums.items():
        gap = _ratio(values[-1], max(values[:-1]))
        assert gap >= MARGIN, (label, gap, values)


def test_an_order_would_not_have_caught_it() -> None:
    """Why the existing contract could not: three luminances a hair
    apart are still in the right order."""

    values = [0.2000, 0.2001, 0.2002]
    assert values[-1] >= max(values[:-1])
    assert _ratio(values[-1], max(values[:-1])) < MARGIN


def test_the_paper_theme_spends_the_budget_mirrored(
    lums: dict[str, list[float]],
) -> None:
    """The reason the margin is smaller on a light theme, recorded so the
    floor is not mistaken for slack: there is almost no room above, so
    scene.py darkens the quiet acts instead."""

    dark = lums["adventure"]
    paper = lums["adventure/paper"]
    assert paper[-1] > dark[-1], (paper[-1], dark[-1])
    assert _ratio(paper[-1], max(paper[:-1])) < _ratio(dark[-1], max(dark[:-1]))
