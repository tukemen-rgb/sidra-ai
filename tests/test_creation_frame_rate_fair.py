"""The clock was honest and the world was not (§26, C-1607).

`requestAnimationFrame` fires at the display's refresh rate - MDN names
75, 120 and 144Hz as widely used - and SIDRA's templates advanced the
world one unit per callback. Driven at three real seconds, the racer
covered 482.92 units at 60Hz and 929.84 at 144Hz (1.93x), while
``ROUND_MS`` reported 3000ms in both, because the round clock is a real
timestamp difference and the world was not.

That made "the same words are the same fight" - the seeded promise every
template makes - true only between two devices that happen to refresh
alike, and quietly raised the difficulty on the faster one.

``TICK(now)`` in the shared preamble is §26's accumulator. These tests
pin the property from the player's side: how far the course travels in a
second of real time.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.animation import tick_probe
from sidra_ai.creation.racing import rate_probe

#: Every template, since the gate is shared (C-1608).
_TEMPLATES = {
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
_STEPS: dict[tuple[str, float], dict] = {}


def _steps(template: str, hz: float) -> dict:
    key = (template, hz)
    if key not in _STEPS:
        html = generate_game(_TEMPLATES[template]).html
        script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        run = subprocess.run(
            ["node", "-"],
            input=tick_probe(script, hz=hz),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert run.returncode == 0, run.stderr[:400]
        _STEPS[key] = json.loads(run.stdout.strip().splitlines()[-1])
    return _STEPS[key]

#: One page, driven at several refresh rates. Module-scoped because each
#: rate costs a node run.
_CACHE: dict[tuple[float, float], dict] = {}


def _script() -> str:
    html = generate_game("レースゲームを作って").html
    return re.search(r"<script>(.*?)</script>", html, re.S).group(1)


def _at(hz: float, *, stall_ms: float = 0.0) -> dict:
    key = (hz, stall_ms)
    if key not in _CACHE:
        run = subprocess.run(
            ["node", "-"],
            input=rate_probe(_script(), hz=hz, stall_ms=stall_ms),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert run.returncode == 0, run.stderr[:400]
        _CACHE[key] = json.loads(run.stdout.strip().splitlines()[-1])
    return _CACHE[key]


def test_three_real_seconds_are_three_real_seconds() -> None:
    """The probe measures real time, so the reading means what it says."""

    for hz in (60, 120, 144):
        assert _at(hz)["realMs"] == 3000
        assert _at(hz)["frames"] == round(hz * 3)


@pytest.mark.parametrize("hz", [75, 120, 144])
def test_a_faster_screen_is_not_a_faster_game(hz: int) -> None:
    slow, fast = _at(60)["dist"], _at(hz)["dist"]
    assert slow > 0
    assert fast / slow <= 1.03, (
        f"{hz}Hz covers {fast} where 60Hz covers {slow} in the same three seconds"
    )


def test_every_screen_above_sixty_agrees_exactly() -> None:
    """Not an average: 75, 120 and 144Hz must be the same game."""

    seen = {_at(hz)["dist"] for hz in (75, 120, 144)}
    assert len(seen) == 1, f"the refresh rate still picks the course: {seen}"


def test_a_slow_screen_degrades_into_slow_motion() -> None:
    """§26 事実 4: under load the world slows; it never spirals or rewinds."""

    slow, normal = _at(30)["dist"], _at(60)["dist"]
    assert slow > 0, "the world stopped"
    assert slow <= normal, "a slower screen ran the world faster"


@pytest.mark.parametrize("hz", [75, 120, 144])
def test_a_fast_screen_steps_the_world_exactly_sixty_times_a_second(hz: int) -> None:
    """The property behind the distance: steps, not an average of them.

    A looser bar in TICK would still land inside the 3% above, and would
    step the world 183 times in three seconds instead of 180.
    """

    assert _at(hz)["advanced"] == 180


@pytest.mark.parametrize("hz", [120, 144])
def test_drawing_is_not_gated_with_the_world(hz: int) -> None:
    """A 120Hz screen still gets 120 pictures a second; only the course slows."""

    slow, fast = _at(60)["paints"], _at(hz)["paints"]
    assert slow > 0
    assert fast / slow >= (hz / 60) * 0.9, (
        f"{hz}Hz painted {fast} where 60Hz painted {slow} - the picture was gated too"
    )


def test_a_stalled_tab_does_not_bank_time_and_spend_it() -> None:
    """§26 事実 4: the accumulator has a ceiling, so nothing catches up in a rush."""

    stalled = _at(120, stall_ms=5000)["advanced"]
    assert stalled <= 200, (
        f"after a five-second stall the world took {stalled} steps in three seconds"
    )


@pytest.mark.parametrize("template", sorted(_TEMPLATES))
def test_no_template_runs_the_world_fast_on_a_fast_screen(template: str) -> None:
    """Two real seconds may never buy more than two seconds of world."""

    fast = _steps(template, 120)
    assert fast["realMs"] == 2000
    assert fast["steps"] <= 130, (
        f"{template} stepped {fast['steps']} times in two seconds at 120Hz"
    )


@pytest.mark.parametrize("template", sorted(_TEMPLATES))
def test_no_template_stalls_behind_the_gate(template: str) -> None:
    for hz in (60, 120):
        assert _steps(template, hz)["steps"] >= 100, f"{template} stalled at {hz}Hz"


@pytest.mark.parametrize("template", sorted(_TEMPLATES))
def test_both_screens_play_the_same_game(template: str) -> None:
    """±12 steps of slack: hitstop is still counted in callbacks (C-1614)."""

    slow, fast = _steps(template, 60)["steps"], _steps(template, 120)["steps"]
    assert abs(fast - slow) <= 12, f"{template}: {slow} vs {fast} steps"


@pytest.mark.parametrize("template", sorted(_TEMPLATES))
def test_only_the_world_is_gated_never_the_picture(template: str) -> None:
    slow, fast = _steps(template, 60)["paints"], _steps(template, 120)["paints"]
    assert slow > 0
    assert fast / slow >= 1.8, f"{template} painted {fast} vs {slow} - drawing was gated"


@pytest.mark.parametrize("template", sorted(_TEMPLATES))
def test_every_callback_asks_the_gate(template: str) -> None:
    """A template that dropped the gate reads as a stall, not as a sprint."""

    for hz in (60, 120):
        got = _steps(template, hz)
        # hitstop swallows a callback before the gate is reached, and is
        # still counted in callbacks rather than time (C-1614) - measured
        # at 8 in three seconds at worst. A template that dropped the gate
        # misses all 120 or 240.
        missed = got["frames"] - got["calls"]
        assert missed <= 20, (
            f"{template} at {hz}Hz asked {got['calls']} times in {got['frames']} frames"
        )


@pytest.mark.parametrize(
    "template", ["shooter", "kaiju", "marble", "catch", "racing"]
)
def test_the_worlds_own_clock_agrees(template: str) -> None:
    """The five templates that keep a clock of their own (C-1612: the
    other five keep none, so a page that asks the gate and ignores the
    answer is not caught here)."""

    slow, fast = _steps(template, 60), _steps(template, 120)
    assert fast["world"] is not None
    assert fast["world"] <= 130, f"{template}: world advanced {fast['world']}"
    assert abs(fast["world"] - slow["world"]) <= 12
