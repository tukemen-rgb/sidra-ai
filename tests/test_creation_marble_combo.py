"""C-1420: the third template with a run, and the sum that keeps it legible.

combo.py's unwired table said marble needed a decision before it could be
wired: C-1313 had made some gates worth double, and two multipliers at once
is one too many. The decision taken here is that **the run multiplies the
gate's base value and the hot gate's extra is added outside it** - a hot
gate on a x3 run pays 3 + 1, not 6.

Stacking them would make the best line on the course the one a player
cannot work out from the seat, which is what §13's readable risk is
against. It is also the call C-1411 already made when it added the graze to
the kills rather than multiplying the two together.

One correction to the entry, recorded because the next person will read it:
it said the run breaks on 「落下」. There is no fall in that corridor. The
only way off the course is a block, and that ends the go outright - so a
gate passed outside the posts is the one thing a player can do wrong and
keep playing, which is what a run has to be breakable by.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.combo import COMBO_MAX, COMBO_STEP, COMBO_TEMPLATES, COMBO_UNWIRED
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.marble import GATE_BASE, combo_probe_source


def _script() -> str:
    body = re.search(
        r"<script>(.*?)</script>",
        generate_game("玉転がしを作って", template="marble").html,
        re.S,
    )
    assert body is not None
    return body.group(1)


def _roll(**kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to roll the corridor")
    probe = subprocess.run(
        ["node", "-"],
        input=combo_probe_source(_script(), **kwargs),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:500]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def clean() -> dict:
    return _roll(mode="run")


@pytest.fixture(scope="module")
def skipped() -> dict:
    return _roll(mode="skip")


def _through(run: dict) -> list[dict]:
    return [event for event in run["events"] if event["kind"] == "through"]


# --- the table -------------------------------------------------------------


def test_marble_is_wired_and_no_longer_excused() -> None:
    assert "marble" in COMBO_TEMPLATES
    assert "marble" not in COMBO_UNWIRED


# --- the ladder ------------------------------------------------------------


def test_consecutive_gates_build_the_run(clean: dict) -> None:
    through = _through(clean)
    assert through
    assert max(event["mult"] for event in through) > 1


def test_the_ladder_uses_its_own_step_and_cap(clean: dict) -> None:
    for event in _through(clean):
        assert event["mult"] == min(COMBO_MAX, 1 + event["run"] // COMBO_STEP)
    assert max(event["mult"] for event in _through(clean)) <= COMBO_MAX


# --- the decision ----------------------------------------------------------


def test_every_payment_is_the_sum_and_not_the_product(clean: dict) -> None:
    for event in _through(clean):
        expected = GATE_BASE * event["mult"] + (GATE_BASE if event["hot"] else 0)
        assert event["paid"] == expected, event


def test_a_hot_gate_on_a_built_run_actually_happened(clean: dict) -> None:
    # Without one, the sum and the product agree and the test above proves
    # nothing about the decision.
    stacked = [e for e in _through(clean) if e["hot"] and e["mult"] > 1]
    assert stacked, "no hot gate landed on a built run"
    for event in stacked:
        assert event["paid"] != GATE_BASE * 2 * event["mult"]


# --- and what takes it away ------------------------------------------------


def test_a_missed_gate_takes_the_whole_run(skipped: dict) -> None:
    missed = [event for event in skipped["events"] if event["kind"] == "past"]
    assert missed
    assert all(event["run"] == 0 and event["mult"] == 1 for event in missed)


def test_the_skipping_roll_had_something_to_lose(skipped: dict) -> None:
    assert max(event["mult"] for event in skipped["events"]) > 1


# --- and what stays on screen ----------------------------------------------


def test_the_multiplier_is_shown_at_one_as_much_as_at_four(clean: dict) -> None:
    huds = [event["hud"] for event in _through(clean) if event["hud"]]
    assert huds
    assert all("×" in hud for hud in huds)
    assert [hud for hud in huds if "×1" in hud]


def test_reduced_motion_keeps_the_number() -> None:
    quiet = _roll(mode="run", reduced=True)
    assert max(event["mult"] for event in quiet["events"]) > 1
