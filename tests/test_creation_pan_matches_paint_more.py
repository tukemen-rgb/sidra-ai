"""The other panned sites (§28 Intermediate, C-1653).

C-1650 opened this contract on one site. The reason for not stopping there
is that the same shape has now gone wrong twice: C-1633 found one channel
handed the event's x and another handed a different object's, and C-1650
found racing's slipstream telling the ear 482px while the eye painted
448px. Source reading is not enough - that is the ledger C-1640 stopped
trusting, and in C-1652 a template that looked right in the source turned
out to be reading another event's kick once actually driven.

Two pages do not share a coordinate space between the channels, and that
is design rather than fault: the platformer pans camera-relative while its
light is a world x, and the marble pans by lane because the projection at
gate range would saturate the panner. The first is mapped; the second is
left out on purpose, so a correct implementation is not failed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import knock_probe
from sidra_ai.creation.duel import ladder_probe as duel_ladder
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.platformer import ladder_probe as plat_ladder
from sidra_ai.creation.shooter import ladder_probe as shooter_ladder

CASES = (
    ("冒険ゲームを作って", knock_probe, "adventure"),
    ("ジャンプで進むゲームを作って", plat_ladder, "platformer"),
    ("シューティングゲームを作って", shooter_ladder, "shooter"),
    ("ビームで撃ち合うゲームを作って", duel_ladder, "duel"),
)


def _pair(request: str, builder) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
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
    return json.loads(probe.stdout.strip().splitlines()[-1])["pair"]


@pytest.mark.parametrize(("request_", "builder", "name"), CASES, ids=[c[2] for c in CASES])
def test_the_sound_lit_something_on_its_own_frame(request_, builder, name) -> None:
    """A light a second later is not a replication of the sound, and a
    sound that was never driven is not a pass (C-1637)."""

    pair = _pair(request_, builder)

    assert pair is not None, f"{name}: the event was never driven"
    assert not pair["litNothing"], f"{name}: nothing was drawn on that frame"


@pytest.mark.parametrize(("request_", "builder", "name"), CASES, ids=[c[2] for c in CASES])
def test_the_light_lands_where_the_pan_says(request_, builder, name) -> None:
    pair = _pair(request_, builder)

    assert pair["sameSide"], (name, pair)
    assert pair["apartPx"] <= 8, (name, pair)


def test_the_marble_is_left_out_on_purpose() -> None:
    """Its two channels live in different spaces by design - the page says
    why in a comment - so comparing them by position would fail a correct
    implementation. The contract has to say so rather than quietly drop it."""

    import pathlib

    import scripts.product_metrics as _pm  # noqa: F401

    text = pathlib.Path(_pm.__file__).read_text(encoding="utf-8")
    block = text[text.index("creation_pan_matches_paint") :][:3000]

    assert "marble" in block, "the exclusion must be stated where the contract is"
