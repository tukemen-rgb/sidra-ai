"""Holding the charge costs something, and the opponent has a temperament.

Before this, the optimal play was to hold the button forever: the charge bar
stopped silently at full and nothing happened. The opponent also fired on the
same schedule whatever the request said, so learning one fight taught you
nothing about the next. Both are played out in node rather than read, because
"the constant exists" and "the rule bites" are different facts.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.duel import probe_source
from sidra_ai.creation.games import generate_game, validate_game_html

_REQUESTS = (
    "ビームの撃ち合いゲームを作って",
    "エネルギー波バトル作って",
    "必殺技の対戦ゲーム作って",
    "気弾の撃ち合いを作って",
)


def _play(request: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - node is present here
        pytest.skip("node is needed to play the duel")
    script = re.search(r"<script>(.*?)</script>", generate_game(request).html, re.S)
    assert script is not None
    finished = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert finished.returncode == 0, (request, finished.stderr[:400])
    return json.loads(finished.stdout)


def test_never_letting_go_is_punished():
    for request in _REQUESTS:
        seen = _play(request)
        assert seen["peakCharge"] >= 100, request
        assert seen["stunFrames"] > 0, (request, seen)


def test_never_letting_go_actually_loses_the_fight():
    # A stun that cost no ground would be a light show. The fighter who never
    # releases should end up worse off than they started.
    seen = _play(_REQUESTS[0])

    assert seen["hp"] < 3, seen


def test_both_temperaments_are_reachable():
    styles = {_play(request)["style"] for request in _REQUESTS}

    assert styles == {"quick", "charger"}


def test_the_temperament_is_behaviour_and_not_a_label():
    thresholds = {}
    for request in _REQUESTS:
        seen = _play(request)
        thresholds[seen["style"]] = tuple(seen["fire"])

    assert len(set(thresholds.values())) == 2, thresholds
    # A quick draw fires earlier than a charger; if that ever inverts the
    # names on screen would be telling the player the wrong thing.
    assert thresholds["quick"][0] < thresholds["charger"][0]


def test_the_same_request_is_the_same_opponent():
    assert _play(_REQUESTS[0])["style"] == _play(_REQUESTS[0])["style"]


def test_the_opponent_takes_the_same_risk():
    # An enemy immune to the overload would make the rule a penalty on the
    # player rather than a rule of the game.
    page = generate_game(_REQUESTS[0]).html

    assert "overload(e)" in page
    assert "overload(p)" in page


def test_the_push_is_visible_as_a_gauge():
    page = generate_game(_REQUESTS[0]).html

    assert "spark/60" in page


def test_the_page_still_runs():
    for request in _REQUESTS:
        verdict = validate_game_html(generate_game(request).html)
        assert verdict["playable"], (request, verdict["failures"])


def _volleys() -> dict:
    import json as _json
    import re as _re
    import shutil as _shutil
    import subprocess as _subprocess

    import pytest as _pytest

    from sidra_ai.creation.duel import aim_probe
    from sidra_ai.creation.games import generate_game

    if _shutil.which("node") is None:  # pragma: no cover - environment guard
        _pytest.skip("node is required to drive the page")
    page = generate_game("対戦ゲームを作って").html
    script = _re.search(r"<script>(.*?)</script>", page, _re.S)
    assert script is not None
    probe = _subprocess.run(
        ["node", "-"],
        input=aim_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return _json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_shot_goes_where_the_lock_said_with_time_to_react():
    """C-1309: the telegraph tells you where, not only when.

    Played, not grepped: one volley dodged, one taken, both down the lane
    the lock named, both at least 15 frames after it.
    """

    seen = _volleys()

    for volley in (seen["dodged"], seen["stayed"]):
        assert volley is not None, "the opponent locked an aim"
        assert volley["beamLane"] == volley["aimed"]
        assert volley["lockToFire"] >= 15


def test_leaving_the_locked_lane_is_a_dodge_and_staying_is_a_hit():
    seen = _volleys()

    assert seen["dodged"]["hpAfter"] == seen["dodged"]["hpBefore"]
    assert seen["stayed"]["hpAfter"] == seen["stayed"]["hpBefore"] - 1


def _paced(request: str = "ビームで撃ち合うゲームを作って") -> dict:
    """Twelve dodged volleys per act - full health, first blood, match point."""

    import json as _json

    from sidra_ai.creation.duel import pace_probe

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=pace_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return _json.loads(probe.stdout.strip().splitlines()[-1])


def test_match_point_charges_faster_than_the_opening_bell():
    """§6's second-half change (C-1318), measured off the running fight."""

    paced = _paced()
    rates = [paced[act]["rate"] for act in ("opening", "middle", "clutch")]

    assert rates[0] < rates[1] < rates[2], "the fill rate steps with the act"
    assert abs(rates[2] / rates[0] - 1.3) < 0.02
    assert paced["clutch"]["mean"] < paced["opening"]["mean"], (
        "the last act is faster end to end, not only on paper"
    )


def test_the_crescendo_never_eats_the_telegraph():
    """C-1309's fairness survives every act: 15+ frames of locked warning."""

    paced = _paced()

    for act in ("opening", "middle", "clutch"):
        assert paced[act]["minLock"] >= 15, (act, paced[act]["minLock"])
    assert paced["state"] == "play", "a perfect dodger is never hit"


def test_the_flash_never_strobes_past_three_per_second():
    """§15 (WCAG 2.3.1, C-1320): mash fire at match-point tempo, counted."""

    import json as _json

    from sidra_ai.creation.duel import flash_probe

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("ビームで撃ち合うゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=flash_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    seen = _json.loads(probe.stdout.strip().splitlines()[-1])

    assert seen["worstWindow"] <= 3, "no second holds a fourth full-screen flash"
    assert seen["onsets"] >= 5, "the gate limits the strobe, it does not kill the flash"


def test_the_arena_heats_with_the_match():
    """§7 x C-1318 (C-1321): the sky the tempo knows - match point is the
    brightest scene, and the acts actually paint it."""

    paced = _paced()

    assert paced["opening"]["scene"] == 0
    assert paced["middle"]["scene"] == 1
    assert paced["clutch"]["scene"] == 2
    scenes = paced["scenes"]
    assert len(scenes) == 3
    assert len({s["floor"] for s in scenes}) == 3
    assert scenes[2]["lum"] > scenes[0]["lum"]
    assert scenes[2]["lum"] >= scenes[1]["lum"]
