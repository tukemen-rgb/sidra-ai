"""The HUD survives the brightest sky (§4 WCAG 1.4.3, C-1329).

Since §7 the clock-bound rounds save their brightest sky for the final
act, and the themed HUD ink was sinking to ~3:1 against it - theming
cannot help when the tint climbs toward the ink's own luminance. The
templates now draw a plate of the untinted theme surface under the text,
through constants the page reports as its HUD contract; these tests blend
that plate over every measured sky the way the canvas does and hold the
result to WCAG 1.4.3: 4.5:1 for the text, 3:1 for the puzzle's plateless
cursor stroke (the old hardcoded near-white was 1.0:1 on light themes).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import world_probe as adventure_probe
from sidra_ai.creation.catchgame import probe_source as catch_probe
from sidra_ai.creation.duel import pace_probe as duel_probe
from sidra_ai.creation.fishing import probe_source as fishing_probe
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import probe_source as kaiju_probe
from sidra_ai.creation.marble import probe_source as marble_probe
from sidra_ai.creation.platformer import probe_source as platformer_probe
from sidra_ai.creation.puzzle import sky_probe
from sidra_ai.creation.racing import probe_source as racing_probe
from sidra_ai.creation.shooter import probe_source as shooter_probe

_PROBES = {
    "fishing": ("釣りゲームを作って", fishing_probe),
    "catch": ("キャッチゲームを作って", catch_probe),
    "puzzle": ("パズルゲームを作って", sky_probe),
    # C-1334: the same final-act sink, measured on the five templates
    # whose scene probes already play all three acts.
    "adventure": ("迷宮を冒険するゲームを作って", adventure_probe),
    "kaiju": ("巨大怪獣と戦うゲームを作って", kaiju_probe),
    "shooter": ("シューティングゲームを作って", shooter_probe),
    "marble": ("玉転がしゲームを作って", marble_probe),
    "duel": ("ビームで撃ち合うゲームを作って", duel_probe),
    # C-1337: the two RUNNING templates, whose scenes step by lap and by
    # progress. Their contract reports skies[] - the actual per-scene
    # backdrop, which for the platformer is the tinted BG, not the floor.
    "racing": ("レースゲームを作って", racing_probe),
    "platformer": ("ジャンプで進むゲームを作って", platformer_probe),
}


def _lum(hexcolour: str) -> float:
    raw = hexcolour.lstrip("#")
    parts = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _wcag(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _blend(alpha: float, top: str, under: str) -> str:
    t = [int(top.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    u = [int(under.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(round(alpha * a + (1 - alpha) * b) for a, b in zip(t, u))


def _played(template: str, suffix: str = "") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    request, probe = _PROBES[template]
    page = generate_game(f"{request} {suffix}".strip()).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    run = subprocess.run(
        ["node", "-"],
        input=probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", sorted(_PROBES))
def test_the_plated_hud_clears_wcag_in_every_act(template: str) -> None:
    seen = _played(template)
    hud = seen["hud"]

    skies = hud.get("skies")
    for act, sky in enumerate(seen["scenes"]):
        under = skies[act] if skies else sky["floor"]
        backed = _blend(hud["alpha"], hud["plate"], under)
        ratio = _wcag(_lum(hud["ink"]), _lum(backed))
        assert ratio >= 4.5, f"act {act} HUD sinks to {ratio:.2f}"


def test_the_light_theme_is_covered_too(
) -> None:
    """The paper theme is where the old hardcode was invisible."""

    seen = _played("puzzle", "紙のテーマで")
    hud = seen["hud"]

    for act, sky in enumerate(seen["scenes"]):
        backed = _blend(hud["alpha"], hud["plate"], sky["floor"])
        assert _wcag(_lum(hud["ink"]), _lum(backed)) >= 4.5
        stroke = _wcag(_lum(hud["cursor"]), _lum(sky["floor"]))
        assert stroke >= 3.0, f"act {act} cursor sinks to {stroke:.2f}"


def test_the_cursor_is_a_component_on_the_bare_sky() -> None:
    """No plate under the stroke, so it is held to the 3:1 floor."""

    seen = _played("puzzle")
    hud = seen["hud"]

    for act, sky in enumerate(seen["scenes"]):
        stroke = _wcag(_lum(hud["cursor"]), _lum(sky["floor"]))
        assert stroke >= 3.0, f"act {act} cursor sinks to {stroke:.2f}"
