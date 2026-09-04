"""A round nobody played earns nothing.

A page left alone still plays: the race finishes, the basket catches what
falls into it, the monster never swings. The result strip then banked a
personal best and offered a line to paste about it - the product
congratulating somebody for walking away.

**This is about the record, not about making the games unplayable without
input.** C-1404 deliberately made every racing rung finishable untouched,
after measuring that only a no-input beginner could not finish the easy
one; taking that back would undo a decision made on evidence. So an
abandoned round still plays and still ends properly. It simply does not
claim the result was anybody's - no best, no total toward a colour, no
ghost, no streak.
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

from sidra_ai.creation.adapt import streak_probe_source  # noqa: E402
from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402

ASKS = {
    "adventure": "冒険ゲームを作って",
    "catch": "キャッチゲームを作って",
    "duel": "対戦ゲームを作って",
    "fishing": "釣りゲームを作って",
    "kaiju": "怪獣と戦うゲームを作って",
    "marble": "3D のゲームを作って",
    "platformer": "ジャンプアクションを作って",
    "puzzle": "パズルゲームを作って",
    "racing": "レースゲームを作って",
    "shooter": "シューティングゲームを作って",
}

_EXTRA = """    stored: Number(store[ADAPT_KEY] === undefined ? 0 : store[ADAPT_KEY]),
    touched: roundTouched(), score: ROUND_FINAL,
    best: store['sidra.best.'+AFK_KEY_TOKEN] === undefined ? null : store['sidra.best.'+AFK_KEY_TOKEN],
    total: store['sidra.total.'+AFK_KEY_TOKEN] === undefined ? null : store['sidra.total.'+AFK_KEY_TOKEN] });"""


def _round(template: str, *, hold: str | None) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the rounds")
    found = re.search(
        r"<script>(.*?)</script>", generate_game(ASKS[template]).html, re.S
    )
    assert found is not None
    source = streak_probe_source(found.group(1), rounds=1, hold=hold).replace(
        "    stored: Number(store[ADAPT_KEY] === undefined ? 0 : store[ADAPT_KEY]) });",
        _EXTRA.replace("AFK_KEY_TOKEN", json.dumps(template)),
    )
    run = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=240
    )
    assert run.returncode == 0, run.stderr.strip()[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])["rounds"][0]


def test_every_template_is_covered() -> None:
    assert set(ASKS) == set(TEMPLATES)


@pytest.mark.parametrize("template", sorted(ASKS))
def test_an_abandoned_round_banks_nothing(template: str) -> None:
    alone = _round(template, hold=None)

    assert alone["touched"] is False
    assert alone["best"] is None, "a personal best for doing nothing"
    assert alone["total"] is None, "progress toward a colour for doing nothing"
    assert alone["stored"] == 0, "a streak for doing nothing"


@pytest.mark.parametrize("template", sorted(ASKS))
def test_a_played_round_still_banks(template: str) -> None:
    """Or the number above could be had by never recording anything."""

    played = _round(template, hold="ArrowRight")

    assert played["touched"] is True
    assert played["best"] is not None


def test_the_briefing_keypress_is_not_playing() -> None:
    """It is how you get to the game, not playing it. The gate's own
    listener runs first and flips the state inside that very keypress, so
    a listener asking 「are we playing?」 would say yes."""

    assert _round("racing", hold=None)["touched"] is False


def test_an_abandoned_race_still_finishes() -> None:
    """C-1404 stands: the round plays out, it just earns nothing."""

    alone = _round("racing", hold=None)

    assert alone["score"], "the untouched race no longer completes a lap"
