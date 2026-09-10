"""C-1612: five templates kept no clock, so the judge could not tell whether
they obeyed the gate.

``creation_frame_rate_fair`` could already check, on all ten templates, that
every callback asks ``TICK`` and that the gate lets only sixty through a
second. What it could check on *five* is whether the page then did what the
gate said. C-1608's break D5 - puzzle calling ``TICK`` and discarding the
answer - went undetected for exactly this reason: the gate's own count still
read 120/120 while the world ran twice as fast.

The clock is raised by the template, on the line where it commits to
advancing, and that is what makes it evidence. A page that ignored the gate
would raise it on every callback, so 120Hz would read twice 60Hz.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation.animation import tick_probe
from sidra_ai.creation.games import generate_game

ASKS = {
    "shooter": "シューティングゲームを作って",
    "kaiju": "巨大怪獣と戦うゲームを作って",
    "platformer": "ジャンプで進むゲームを作って",
    "adventure": "迷宮を冒険するゲームを作って",
    "duel": "光線で撃ち合う対戦ゲームを作って",
    "puzzle": "パズルゲームを作って",
    "marble": "玉転がしゲームを作って",
    "fishing": "魚釣りゲームを作って",
    "catch": "フルーツキャッチを作って",
    "racing": "レースゲームを作って",
}

#: The five that had none before this item.
WAS_BLIND = ("platformer", "adventure", "duel", "puzzle", "fishing")


def _drive(request: str, hz: float) -> dict:
    body = re.search(r"<script>(.*?)</script>", generate_game(request).html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"], input=tick_probe(body, hz=hz),
        capture_output=True, text=True, timeout=180,
    )
    assert run.returncode == 0, run.stderr.strip()[:200]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", sorted(WAS_BLIND))
def test_the_templates_that_kept_no_clock_now_keep_one(template: str) -> None:
    """Null here is the hole: the judge skips its strongest check."""

    assert _drive(ASKS[template], 60.0)["world"] is not None


@pytest.mark.parametrize("template", sorted(WAS_BLIND))
def test_a_faster_screen_does_not_buy_more_world(template: str) -> None:
    """The check the clock exists for. Two real seconds are two seconds of
    world at either refresh rate."""

    slow = _drive(ASKS[template], 60.0)["world"]
    fast = _drive(ASKS[template], 120.0)["world"]

    # ±2 since C-1614 closed the hitstop asymmetry; these five read 0.
    assert abs(fast - slow) <= 2, f"{template}: {slow} at 60Hz vs {fast} at 120Hz"


def test_the_clock_is_not_the_gates_own_answer() -> None:
    """The two must be able to disagree, or the clock proves nothing.

    ``steps`` is what ``TICK`` returned; ``world`` is what the page then did.
    A template that asked and ignored the answer keeps ``steps`` at 60 a
    second while ``world`` doubles - measured at 120 against 240 with the
    gate's result discarded, where ``steps`` stayed 120/120.
    """

    from sidra_ai.creation.animation import TICK_PROBE

    assert "WORLD_STEPS" in TICK_PROBE or "worldClock" in TICK_PROBE
    slow, fast = _drive(ASKS["puzzle"], 60.0), _drive(ASKS["puzzle"], 120.0)
    assert slow["steps"] == fast["steps"], "the gate itself already disagrees"
    assert abs(fast["world"] - slow["world"]) <= 2
