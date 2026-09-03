"""Open it, press once, play - and next time, don't press at all.

§8 事実 8: explanation, registration and any other cushion between opening
the page and playing it are why people leave. C-1033's briefing screen is
in real tension with that, and it is worth keeping: the three lines are
what the controls *are*, and a game whose objective nobody read is a game
nobody is playing on purpose.

The resolution is not to drop one of them. The first visit gets the
briefing and **any** single input starts the game; every visit after that
opens straight into play, because a briefing is only news once.

"Playable" is measured, not named: it is the template's own callback
receiving frames. A page can call itself 'playing' and still be holding
every frame back, which is exactly what the gate does while it is closed.
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

from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402
from sidra_ai.creation.startscreen import (  # noqa: E402
    FIRST_INPUTS,
    INSTANT_FRAMES,
    start_probe_source,
)
from sidra_ai.creation.tuning import panel_schema  # noqa: E402

KEYS = sorted(TEMPLATES)
CASES = [
    pytest.param(template, kind, key, id=f"{template}-{key or 'tap'}")
    for template in KEYS
    for kind, key in FIRST_INPUTS
]


def _script(template: str) -> str:
    found = re.search(
        r"<script>(.*?)</script>", generate_game("ゲームを作って", template=template).html, re.S
    )
    assert found is not None
    return found.group(1)


def _open(template: str, **kw) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to open the page")
    probe = subprocess.run(
        ["node", "-"],
        input=start_probe_source(_script(template), **kw),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------- the first visit


@pytest.mark.parametrize("template", KEYS)
def test_the_first_visit_gets_its_briefing(template: str) -> None:
    """Untouched, the template has had no frame at all."""

    untouched = _open(template)["untouched"]

    assert untouched["state"] == "title"
    assert untouched["frames"] == 0
    assert untouched["skipped"] is False


@pytest.mark.parametrize(("template", "kind", "key"), CASES)
def test_any_one_input_starts_it(template: str, kind: str, key: str) -> None:
    """"Any key" has to mean any key.

    ``p`` is in the list because it did not: it was the pause key at every
    moment including the title screen, where pausing is meaningless, so a
    player who reached for it first got nothing whatsoever.
    """

    seen = _open(template, kind=kind, key=key)

    assert seen["frames"][0] == INSTANT_FRAMES


@pytest.mark.parametrize("template", KEYS)
def test_starting_is_remembered(template: str) -> None:
    assert _open(template, kind="key", key=" ")["stored"] == [f"sidra.seen.{template}"]


# ------------------------------------------------------------ every visit after


@pytest.mark.parametrize("template", KEYS)
def test_a_return_visit_opens_playing(template: str) -> None:
    untouched = _open(template, stored={f"sidra.seen.{template}": "1"})["untouched"]

    assert untouched["skipped"] is True
    assert untouched["frames"] >= 1, "a return visit still had to be pressed through"


@pytest.mark.parametrize("template", KEYS)
def test_a_page_that_opens_playing_has_not_made_a_sound(template: str) -> None:
    """Browsers refuse audio without a gesture, and a game whose first
    sound is silent teaches the player it has none. Skipping the screen
    skips the press, so the unlock has to wait for a real input."""

    seen = _open(template, stored={f"sidra.seen.{template}": "1"})

    assert seen["untouched"]["gesture"] is False


@pytest.mark.parametrize("template", KEYS)
def test_the_first_input_after_a_skipped_start_unlocks_sound(template: str) -> None:
    seen = _open(template, stored={f"sidra.seen.{template}": "1"}, kind="key", key=" ")

    assert seen["afterInput"]["gesture"] is True


@pytest.mark.parametrize("template", KEYS)
def test_the_briefing_can_be_asked_for_again(template: str) -> None:
    """Skipping is the default, not a decision taken away."""

    untouched = _open(
        template,
        stored={f"sidra.seen.{template}": "1", f"sidra.tune.{template}": {"brief": True}},
    )["untouched"]

    assert untouched["skipped"] is False
    assert untouched["frames"] == 0


# ------------------------------------------------- what the page cannot say


@pytest.mark.parametrize("template", KEYS)
def test_the_panel_carries_the_way_back(template: str) -> None:
    from sidra_ai.creation.games import _DIFFICULTY

    fields = {
        f["key"]: f
        for f in panel_schema(
            template, _DIFFICULTY[template], difficulty="normal", accent="#000000"
        )["fields"]
    }

    assert fields["brief"]["type"] == "flag"
    assert fields["brief"]["default"] is False


def test_the_gate_gets_one_frame_and_no_more() -> None:
    assert INSTANT_FRAMES == 1


def test_the_inputs_tried_include_the_ones_that_were_special() -> None:
    """A list of only ordinary keys would have passed while p was broken."""

    keys = {key for kind, key in FIRST_INPUTS if kind == "key"}

    assert "p" in keys, "the pause key is the one that was not 'any key'"
    assert "ArrowRight" in keys
    assert any(kind == "tap" for kind, _ in FIRST_INPUTS), "a phone has only taps"
