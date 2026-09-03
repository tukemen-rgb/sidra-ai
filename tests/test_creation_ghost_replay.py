"""The run that set the record, played back beside this one.

§11 事実 1: racing your own ghost raises effort, enjoyment and
self-efficacy, and two ghosts beat one. The personal best already existed
(C-1106) as a number on a strip - there was no way to play *with* the run
behind it.

Two assertions carry the item, and neither is "a ghost exists":

* **It is a memory, not a second car.** With the ghost on, the car's own
  path through the course is bit-for-bit what it is with the ghost off.
  Comparing lap counts was not enough - a deliberate break that dragged
  the car by half a percent kept the lap count and changed the race.
* **It appears only when there is a past.** The first run draws none and
  saves a trail; the second draws one.
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

from sidra_ai.creation.games import TEMPLATES, _DIFFICULTY, generate_game  # noqa: E402
from sidra_ai.creation.ghost import (  # noqa: E402
    GHOST_PREAMBLE,
    GHOST_STEP,
    GHOST_TEMPLATES,
    GHOST_UNWIRED,
    PREAMBLE_NAMES,
)
from sidra_ai.creation.together import STORAGE_PREFIXES, probe_source  # noqa: E402
from sidra_ai.creation.tuning import SPEED_BINDING, panel_schema  # noqa: E402

TEMPLATE = GHOST_TEMPLATES[0]
REQUEST = "レースゲームを作って"


def _script() -> str:
    found = re.search(
        r"<script>(.*?)</script>", generate_game(REQUEST, template=TEMPLATE).html, re.S
    )
    assert found is not None
    return found.group(1)


def _run(stored: dict) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive two runs")
    source = probe_source(
        _script(), speed_expr=SPEED_BINDING[TEMPLATE], frames=3800, stored=stored
    ).replace(
        "  writes: [...new Set(allWrites)].sort(),",
        "  writes: [...new Set(allWrites)].sort(), ghost: ghostFacts(),"
        f" trail: allStored['sidra.ghost.{TEMPLATE}']||null,",
    )
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=300
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def runs() -> dict:
    base = {f"sidra.seen.{TEMPLATE}": "1"}
    first = _run(dict(base))
    carried = {**base, f"sidra.ghost.{TEMPLATE}": first["trail"]}
    return {
        "first": first,
        "second": _run(dict(carried)),
        "off": _run({**carried, f"sidra.tune.{TEMPLATE}": {"ghost": False}}),
    }


# ------------------------------------------------------------- the two claims


def test_the_ghost_is_a_memory_and_not_a_second_car(runs: dict) -> None:
    """The car's own path, with the ghost and without it.

    A lap count was the first thing this compared, and a break that
    dragged the car by half a percent kept the lap count. The path is what
    the claim is about.
    """

    assert runs["second"]["ghost"]["runHash"] == runs["off"]["ghost"]["runHash"]
    assert runs["second"]["facts"]["round"]["score"] == runs["first"]["facts"]["round"]["score"]


def test_it_appears_only_once_there_is_a_past(runs: dict) -> None:
    assert runs["first"]["ghost"]["had"] is False
    assert runs["first"]["ghost"]["drawn"] == 0
    assert runs["second"]["ghost"]["had"] is True
    assert runs["second"]["ghost"]["drawn"] > 0


def test_the_ghost_is_actually_drawn(runs: dict) -> None:
    """Counted calls are not pixels: the drawn geometry has to differ."""

    assert runs["second"]["geometry"] != runs["first"]["geometry"]


def test_the_switch_puts_it_away_completely(runs: dict) -> None:
    """Not "mostly": with the ghost off the page draws what it drew before
    there was one, exactly."""

    assert runs["off"]["ghost"]["drawn"] == 0
    assert runs["off"]["geometry"] == runs["first"]["geometry"]


def test_the_record_run_leaves_a_trail(runs: dict) -> None:
    first = runs["first"]

    assert first["ghost"]["saved"] == 1
    assert first["ghost"]["samples"] > 0
    assert len(json.loads(first["trail"])) == first["ghost"]["stored"]


# ------------------------------------------------- what the page cannot say


def test_the_trail_is_indexed_by_the_course_not_the_clock() -> None:
    """A time-keyed trail slides out of step the moment a run is faster,
    and then the ghost means nothing."""

    assert "function ghostBucket(progress){" in GHOST_PREAMBLE
    assert "Math.floor(progress/GHOST_STEP)" in GHOST_PREAMBLE
    assert GHOST_STEP > 0


def test_the_panel_carries_the_switch_on_by_default() -> None:
    fields = {
        f["key"]: f
        for f in panel_schema(
            TEMPLATE, _DIFFICULTY[TEMPLATE], difficulty="normal", accent="#000000"
        )["fields"]
    }

    assert fields["ghost"]["type"] == "flag"
    assert fields["ghost"]["default"] is True, "a past self nobody meets is not one"


def test_the_trail_never_leaves_the_machine() -> None:
    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket"):
        assert banned not in GHOST_PREAMBLE


def test_the_storage_key_is_declared_like_every_other() -> None:
    assert "sidra.ghost." in STORAGE_PREFIXES


def test_every_template_is_wired_or_has_a_reason() -> None:
    """A template with no progress axis has nothing to index a trail by,
    and saying which is which is the deliverable for the next one."""

    assert set(GHOST_TEMPLATES) | set(GHOST_UNWIRED) == set(TEMPLATES)
    assert not set(GHOST_TEMPLATES) & set(GHOST_UNWIRED)
    for reason in GHOST_UNWIRED.values():
        assert len(reason) > 30, "a template skipped with no reason is a template forgotten"


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_no_template_shadows_a_ghost_name(template: str) -> None:
    body = TEMPLATES[template].script
    for name in PREAMBLE_NAMES:
        assert f"function {name}(" not in body
        assert f"const {name}=" not in body
        assert f"let {name}=" not in body
