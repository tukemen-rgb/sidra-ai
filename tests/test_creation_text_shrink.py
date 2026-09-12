"""A word keeps its size when the glass shrinks (§24, C-1725).

§24 says the type floor has to be decided in *effective* size, because a
canvas pixel shrinks with the page - and then picked 13px from the
smallest promoted **landscape** screen (667px, x0.926, so 12.0 effective,
over iOS's 11pt Caption 2).

§18's own 学び says the rotation prompt is 案内であって遮断ではない, and
C-1720 spent a cycle fitting the pad to portrait at 390 CSS px. Portrait
is a play mode this product supports, and there the scale is 1.846: 13
canvas px is 7.04 effective, and even the 20px headline is 10.8 - under
the floor §24 quotes.

The pad has kept a thumb's width constant since C-1019 and through
C-1720. Nothing did the same for a word: the mechanism was already on the
page - ``padScale()`` - and simply not wired to the eye.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.hudpaint import textsize_probe

FLOOR = 11.0  # §24 事実 2: iOS Caption 2
REQUESTS = {
    "adventure": "迷宮を冒険するゲームを作って",
    "duel": "ビームで撃ち合うゲームを作って",
    "kaiju": "巨大怪獣と戦うゲームを作って",
    "shooter": "シューティングゲームを作って",
    "puzzle": "パズルゲームを作って",
    "platformer": "ジャンプで進むゲームを作って",
    "marble": "玉転がしゲームを作って",
    "racing": "レースゲームを作って",
    "fishing": "釣りゲームを作って",
    "catch": "落ちものをキャッチするゲームを作って",
}


def read(key: str, css_w: int) -> dict:
    found = re.search(r"<script>(.*?)</script>", generate_game(REQUESTS[key]).html, re.S)
    assert found is not None, key
    got = subprocess.run(
        ["node", "-"],
        input=textsize_probe(found.group(1), css_w=css_w),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert got.returncode == 0, (key, css_w, got.stderr[:400])
    return json.loads(got.stdout.strip().splitlines()[-1])


def boxes(seen: dict) -> dict:
    out: dict = {}
    for where in ("title", "played"):
        for name, box in (seen.get(where) or {}).items():
            assert name != "?", "a word was drawn with no font at all"
            keep = out.setdefault(name, dict(box))
            keep["longest"] = max(keep["longest"], box["longest"])
    return out


@pytest.fixture(scope="module")
def narrow() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to draw the words")
    return {key: boxes(read(key, 360)) for key in REQUESTS}


@pytest.fixture(scope="module")
def desk() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to draw the words")
    return {key: boxes(read(key, 720)) for key in REQUESTS}


@pytest.mark.parametrize("key", sorted(REQUESTS))
def test_every_word_clears_the_floor_on_the_narrowest_phone(
    narrow: dict, key: str
) -> None:
    found = narrow[key]
    assert found, "nothing was written, so nothing is proved"
    for box in found.values():
        assert box["effective"] >= FLOOR - 0.01, (key, box)


@pytest.mark.parametrize("key", sorted(REQUESTS))
def test_raising_the_type_does_not_push_a_line_off_the_canvas(
    narrow: dict, key: str
) -> None:
    """Monospace, so a full-width character is one em wide."""

    for box in narrow[key].values():
        assert box["longest"] * box["px"] <= 720, (key, box)


@pytest.mark.parametrize("key", sorted(REQUESTS))
def test_the_words_box_is_on_the_glass(narrow: dict, desk: dict, key: str) -> None:
    """C-1726. Raising the type and checking only its width missed the
    thing it sits on: the HUD plates and baselines were canvas-pixel
    numbers written for 13px type, so at 360 CSS px adventure drew a 22px
    line on a 16px plate with its cap 6.6px above the canvas - off the
    bitmap, and not drawn at all."""

    for where, found in (("360", narrow[key]), ("720", desk[key])):
        for box in found.values():
            assert box["top"] >= -0.01, (key, where, box)
            assert box["bottom"] <= 320.01, (key, where, box)


def top_level_args(text: str) -> list[str]:
    """Split on commas that are not inside a nested call - hudBand(13,3)
    is one argument, not two."""

    out, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(text[start:i])
            start = i + 1
    out.append(text[start:])
    return out


BODIES = {
    "adventure": ("sidra_ai.creation.adventure", "ADVENTURE_SCRIPT"),
    "duel": ("sidra_ai.creation.duel", "DUEL_SCRIPT"),
    "kaiju": ("sidra_ai.creation.kaiju", "KAIJU_SCRIPT"),
    "platformer": ("sidra_ai.creation.platformer", "PLATFORMER_SCRIPT"),
    "shooter": ("sidra_ai.creation.shooter", "SHOOTER_SCRIPT"),
    "puzzle": ("sidra_ai.creation.puzzle", "PUZZLE_SCRIPT"),
    "marble": ("sidra_ai.creation.marble", "MARBLE_SCRIPT"),
    "racing": ("sidra_ai.creation.racing", "RACING_SCRIPT"),
    "fishing": ("sidra_ai.creation.games", "_FISHING"),
    "catch": ("sidra_ai.creation.games", "_CATCH"),
}


@pytest.mark.parametrize("key", sorted(BODIES))
def test_the_plate_is_sized_from_the_type_it_holds(key: str) -> None:
    """Two geometric rules were tried for this and measurement withdrew
    both: "the plate is the rect at a partial alpha" also catches every
    particle and scrim, and "a monospace line is len x px wide"
    over-counts by half on 「得点 9 ×1」. What is left is the rule that can
    be checked exactly - a plate written as a number cannot follow the
    type it holds (C-1342)."""

    import importlib

    where, name = BODIES[key]
    body = getattr(importlib.import_module(where), name)
    for line in re.findall(r"fillStyle=HUD_PLATE;\s*\n?\s*(.*)", body):
        for rect in re.finditer(r"fillRect\(([^;]*?)\);", line):
            args = top_level_args(rect.group(1))
            if len(args) >= 4:
                assert "hudBand(" in args[-1], (key, rect.group(0))
    if "const HSB=" in body:
        assert "const HSB=hudBand(" in body, key


def test_the_plate_grows_with_the_type_it_holds() -> None:
    """One helper, beside the one it borrows from, so a plate and its
    words cannot drift apart (C-1342)."""

    from sidra_ai.creation import touchpad

    assert "function hudBand(px,pad){return hudPx(px)+pad}" in touchpad.PAD_PREAMBLE


@pytest.mark.parametrize("key", sorted(REQUESTS))
def test_the_desk_is_untouched(desk: dict, key: str) -> None:
    """The other direction. Raising every font until (a) passes would be a
    different product; on a desk the scale is 1 and max(px, 11) is px."""

    found = desk[key]
    assert found, key
    assert min(b["px"] for b in found.values()) >= 13, found
    assert max(b["px"] for b in found.values()) <= 22, found


def test_the_floor_is_named_beside_the_scale_that_protects_the_thumb() -> None:
    """One constant, next to the mechanism it borrows, so the two cannot
    drift (C-1342)."""

    from sidra_ai.creation import touchpad

    assert "const TEXT_FLOOR=11;" in touchpad.PAD_PREAMBLE
    assert "function hudPx(px){return Math.max(px,TEXT_FLOOR*padScale())}" in (
        touchpad.PAD_PREAMBLE
    )


def test_no_template_still_spells_a_raw_font_size() -> None:
    """The census C-1375 kept was a regex over `font='13px`; every one of
    those now goes through hudPx, and a new one must too."""

    page = generate_game("迷宮を冒険するゲームを作って").html
    assert "hudPx(" in page
    assert not re.search(r"\.font='\d+px", page), re.findall(r"\.font='\d+px", page)[:3]
