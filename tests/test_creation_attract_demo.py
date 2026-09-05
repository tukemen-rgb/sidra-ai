"""C-1414: the title screen with the game running behind it.

§17 is about arcade attract modes: the cabinet plays itself so a passer-by
can see what the game *is* before committing. The gate (C-1111) deliberately
gave the template not one frame until somebody pressed, which is the right
default and the reason the demo needs wiring rather than a flag.

What these tests are for, beyond the judge: the judge measures the one wired
template end to end. These pin the boundaries around it - that the unwired
table accounts for every other template, that an unwired page is byte-for-byte
the gate it always was, and that the three shared things a demo can dirty
(the round clock, the bank, the trail) stay clean without needing a
four-thousand-frame run to notice.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.attract import (
    ATTRACT_RESET,
    ATTRACT_TEMPLATES,
    ATTRACT_UNWIRED,
    probe_source,
    reset_call,
    wired,
)
from sidra_ai.creation.games import TEMPLATES, generate_game


def _script(template: str) -> str:
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S)
    assert body is not None
    return body.group(1)


def _watch(template: str, **kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to watch the title screen")
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(_script(template), **kwargs),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:500]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def demo() -> dict:
    """Racing, left alone for two seconds and then started."""

    return _watch("racing", idle=120, play=30)


@pytest.fixture(scope="module")
def still() -> dict:
    """An unwired template, left alone for the same two seconds."""

    return _watch("catch", idle=120, play=30)


@pytest.fixture(scope="module")
def piloted() -> dict:
    """Shooter (C-1338): the demo whose hand holds the trigger.

    Forty seconds, because the shooter's demo ends by losing its own
    ship - the first life lasts over twenty - and the loop back to
    another go is part of the claim.
    """

    return _watch("shooter", idle=2400, play=30)


# --- the table -------------------------------------------------------------


def test_every_template_is_either_wired_or_explained() -> None:
    assert set(ATTRACT_TEMPLATES) | set(ATTRACT_UNWIRED) == set(TEMPLATES)
    assert not set(ATTRACT_TEMPLATES) & set(ATTRACT_UNWIRED)


def test_each_unwired_reason_says_something() -> None:
    for template, reason in ATTRACT_UNWIRED.items():
        assert len(reason) > 20, template
        assert not reason.endswith("."), template


def test_wired_needs_both_the_list_and_a_way_back_to_frame_one() -> None:
    for template in ATTRACT_TEMPLATES:
        assert template in ATTRACT_RESET
        assert wired(template)
        assert reset_call(template)
    # Listed but with no reset is not wired: a demo that cannot be rewound
    # would hand the player the middle of the go they just watched.
    assert not wired("catch")
    assert reset_call("catch") == ""


# --- what reaches the page -------------------------------------------------


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_no_attract_token_survives_into_a_page(template: str) -> None:
    body = _script(template)
    assert "ATTRACT_WIRED_TOKEN" not in body
    assert "ATTRACT_RESET_TOKEN" not in body
    assert f"const ATTRACT_WIRED={'true' if wired(template) else 'false'};" in body


def test_the_wired_page_names_its_own_way_back() -> None:
    assert "try{reset()}catch(e){}" in _script("racing")


def test_the_pilot_line_is_substituted_per_template() -> None:
    """The shooter's page carries its one held input; racing carries none."""

    assert "try{fire=true;if(kills>0)ATTRACT_LIVE=1}catch(e){}" in _script("shooter")
    assert "fire=true" not in _script("racing")
    assert "ATTRACT_PILOT_TOKEN" not in _script("shooter")
    assert "ATTRACT_PILOT_TOKEN" not in _script("racing")


def test_the_piloted_demo_shoots_loses_and_goes_again(piloted: dict) -> None:
    """The held trigger makes a demo with a game in it (C-1338).

    The picture moves, the demo reaches its own end at least once and
    loops instead of freezing on the over screen, and none of it started
    the round clock or wrote anything down.
    """

    facts = piloted["beforePress"]["attract"]
    assert facts["wired"] is True
    assert facts["frames"] == 2400
    assert facts["loops"] >= 1, "the demo never lost its own ship"
    assert facts["live"] == 1, "the demo never shot anything down"
    hashes = [frame["hash"] for frame in piloted["idle"]]
    assert len(set(hashes)) > 2160, "the picture barely moved"
    assert piloted["beforePress"]["round"]["ms"] == 0
    assert piloted["beforePress"]["touched"] is False
    assert sorted(piloted["beforePress"]["store"]) == []


def test_the_press_after_a_piloted_demo_matches_the_control(piloted: dict) -> None:
    """The handover lets go of the trigger: the go starts from the top."""

    control = _watch("shooter", idle=0, play=30)

    def _snap(run: dict, at: str) -> dict:
        out = {k: v for k, v in run[at].items() if k != "attract"}
        out["round"] = dict(out["round"], ms=round(out["round"]["ms"]))
        return out

    assert _snap(piloted, "atPress") == _snap(control, "atPress")
    assert _snap(piloted, "afterPlay") == _snap(control, "afterPlay")


# --- the demo itself -------------------------------------------------------


def test_the_demo_runs_behind_the_title(demo: dict) -> None:
    facts = demo["beforePress"]["attract"]
    assert facts["wired"] is True
    assert facts["frames"] == 120
    hashes = [frame["hash"] for frame in demo["idle"]]
    assert len(set(hashes)) == len(hashes), "the demo drew the same picture twice"


def test_the_gate_still_gave_the_player_nothing(demo: dict) -> None:
    # GATE_RAN is the frames a *player* has been handed. The demo's are not
    # the player's, and every start-screen number is read off this one.
    assert demo["beforePress"]["gate"]["frames"] == 0
    assert demo["beforePress"]["gate"]["state"] == "title"


def test_the_loop_does_not_multiply(demo: dict) -> None:
    assert max(frame["calls"] for frame in demo["idle"]) == 1


def test_an_unwired_title_is_one_still_picture(still: dict) -> None:
    assert still["beforePress"]["attract"] == {
        "wired": False, "frames": 0, "loops": 0, "live": 0}
    assert len({frame["hash"] for frame in still["idle"]}) == 1


# --- and what it is not allowed to take ------------------------------------


def test_the_round_clock_does_not_run_behind_the_title(demo: dict) -> None:
    clock = demo["beforePress"]["round"]
    assert clock["ms"] == 0
    assert clock["done"] is False
    assert demo["beforePress"]["touched"] is False


def test_the_demo_writes_nothing_down(demo: dict) -> None:
    assert demo["beforePress"]["store"] == {}
    assert demo["beforePress"]["round"]["best"] is None
    assert demo["beforePress"]["round"]["score"] is None


def test_the_press_hands_over_a_go_that_starts_at_the_top(demo: dict) -> None:
    race = demo["atPress"]["race"]
    assert (race["dist"], race["lap"], race["times"], race["lapT"]) == (0, 1, [], 0)
    assert (race["passed"], race["slips"]) == (0, 0)
    assert race["spd"] == race["base"]
    # The trail the demo sampled is the demo's, and a ghost is banked with
    # the score it belongs to (C-1401) - so it must not be carrying the
    # demo's positions when the player's own run starts.
    assert demo["atPress"]["ghost"]["samples"] == 0


def test_the_same_page_runs_the_same_after_a_demo() -> None:
    """The world SEED promises is the world you get, demo or no demo.

    Not visible at the instant of the press: the obstacle list is empty in
    both runs, and the random stream they come out of is not in any facts
    function. It shows a couple of hundred frames in, which is where the
    first obstacles are placed.
    """

    watched = _watch("racing", idle=600, play=240)
    control = _watch("racing", idle=0, play=240)
    assert watched["afterPlay"]["race"] == control["afterPlay"]["race"]
    assert watched["afterPlay"]["ghost"] == control["afterPlay"]["ghost"]
