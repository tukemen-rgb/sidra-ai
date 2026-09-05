"""C-1426: the fishing run, and the sweep that does not break it.

``COMBO_UNWIRED`` had this template down as needing "a rule for the idle
sweep between casts" before the ladder could be wired to it. The rule this
settles on: **the sweep is not a miss.** Only a cast breaks the run,
because waiting for the marker to come back around is exactly what the
game asks a player to do, and a run that drained while they waited would
make patience the punished move.

Everything below is read off one real go on the generated page, driven by
pressing at measured offsets from the spot - never by re-implementing the
arithmetic. The ladder the casts are checked against is derived here from
``COMBO_STEP``/``COMBO_MAX`` rather than from what the page says its own
multiplier is.
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

from sidra_ai.creation.combo import (  # noqa: E402
    COMBO_MAX,
    COMBO_STEP,
    COMBO_TEMPLATES,
    COMBO_UNWIRED,
)
from sidra_ai.creation.fishing import combo_probe_source  # noqa: E402
from sidra_ai.creation.games import generate_game  # noqa: E402

ASK = "釣りゲームを作って"


def rung(run_length: int) -> int:
    """The documented ladder, told the length of a run."""

    return min(COMBO_MAX, 1 + run_length // COMBO_STEP)


def test_the_template_is_wired_rather_than_excused() -> None:
    assert "fishing" in COMBO_TEMPLATES
    assert "fishing" not in COMBO_UNWIRED


@pytest.fixture(scope="module")
def played():
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the round")
    found = re.search(r"<script>(.*?)</script>", generate_game(ASK).html, re.S)
    assert found is not None
    run = subprocess.run(
        ["node", "-"],
        input=combo_probe_source(found.group(1)),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_consecutive_casts_climb_the_ladder(played) -> None:
    tops = [c["multAfter"] for c in played["timeline"]]
    assert tops, "no casts were landed"
    assert max(tops) >= 2, f"the run never left the bottom rung ({tops})"
    for cast in played["timeline"]:
        assert cast["multAfter"] == rung(cast["runAfter"]), cast


def test_each_cast_pays_base_times_multiplier(played) -> None:
    for cast in played["timeline"]:
        assert cast["gain"] == rung(cast["runAfter"]), cast


def test_sweeping_without_casting_does_not_break_the_run(played) -> None:
    """The decision this item existed to make."""

    before, after = played["idleBefore"], played["idleAfter"]
    # "Nothing changed" is only a result if time actually passed.
    assert after["ms"] > before["ms"]
    assert after["casts"] == before["casts"]
    assert (after["run"], after["mult"]) == (before["run"], before["mult"])


def test_the_perfect_throw_is_added_outside_the_multiplier(played) -> None:
    """A 会心 on a x3 run pays 3 + 1, not 6 - the C-1420 sum."""

    perfect = played["perfect"]
    assert perfect["crits"] >= 1
    assert perfect["multBefore"] >= 2, "the sum is vacuous at x1"
    assert perfect["gain"] == rung(perfect["runAfter"]) + 1


def test_a_cast_outside_the_band_takes_all_of_it(played) -> None:
    whiff = played["whiff"]
    assert whiff["multBefore"] >= 2, "nothing was there to lose"
    assert whiff["gain"] == 0
    assert (whiff["runAfter"], whiff["multAfter"]) == (0, 1)


def test_it_climbs_again_from_one(played) -> None:
    again = played["rebuilt"]
    assert again, "nothing was cast after the break"
    assert again[0]["multAfter"] == 1
    assert max(c["multAfter"] for c in again) >= 2


def test_the_multiplier_is_on_screen_at_one_as_much_as_at_the_top(played) -> None:
    """Asked of the lines the page drew, not of the source."""

    shown = {c["multAfter"]: c["hud"] for c in played["timeline"] if c["hud"]}
    assert shown, "the HUD never drew its score line"
    top = max(shown)
    assert "×1" in (shown.get(1) or ""), shown.get(1)
    assert f"×{top}" in shown[top], shown[top]
