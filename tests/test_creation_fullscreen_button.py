"""C-1416: the button that makes the game as big as the screen.

§18 事実 2: a phone gives about 40% of its screen to the URL bar and this
page's own margins. Fullscreen takes it back - for somebody who asked, on a
browser that will honour it.

What these tests pin that the judge does not: the judge drives four
browsers and asks what the page did. These ask what the page *is* - that
the wrapper and the button are really in the document (the probe supplies
its own, so nothing it measures can see this), that the button is off until
the script turns it on, and that a page whose script never ran offers
nothing rather than offering something dead.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.fullscreen import (
    BUTTON_ID,
    LABEL_ENTER,
    LABEL_EXIT,
    LOCK_TO,
    WRAP_ID,
    preamble,
    probe_source,
)
from sidra_ai.creation.games import TEMPLATES, generate_game


def _page(template: str = "racing") -> str:
    return generate_game("ゲームを作って", template=template).html


def _script(page: str) -> str:
    body = re.search(r"<script>(.*?)</script>", page, re.S)
    assert body is not None
    return body.group(1)


def _drive(**kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to press the button")
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(_script(_page()), **kwargs),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:500]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def granted() -> dict:
    return _drive()


@pytest.fixture(scope="module")
def refused() -> dict:
    return _drive(grant=False)


# --- what is in the page ---------------------------------------------------


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_page_carries_the_wrapper_and_the_button(template: str) -> None:
    page = _page(template)
    assert page.count(f'id="{WRAP_ID}"') == 1
    assert page.count(f'id="{BUTTON_ID}"') == 1
    assert LABEL_ENTER in page


def test_the_canvas_is_inside_the_wrapper() -> None:
    # The wrapper is what goes fullscreen. If the canvas were outside it,
    # the request would blank the screen instead of filling it with the
    # game; if the button were outside it, there would be no way back.
    page = _page()
    inside = re.search(rf'<div class="stagewrap" id="{WRAP_ID}">(.*?)</div>', page, re.S)
    assert inside is not None
    assert 'id="stage"' in inside.group(1)
    assert f'id="{BUTTON_ID}"' in inside.group(1)


def test_the_button_starts_hidden_in_the_stylesheet() -> None:
    # Progressive addition: the script turns it on where the browser says
    # it will work, so a page whose script never ran shows nothing rather
    # than a button that opens nothing.
    rules = re.findall(r"\.fullbtn\{[^}]*\}", _page())
    assert rules
    assert all("display:none" in rule for rule in rules)


def test_no_fullscreen_token_survives_into_a_page() -> None:
    body = _script(_page())
    for token in ("FULL_WRAP_TOKEN", "FULL_BTN_TOKEN", "FULL_ENTER_TOKEN",
                  "FULL_EXIT_TOKEN", "FULL_LOCK_TOKEN"):
        assert token not in body
    assert LABEL_EXIT in body


def test_the_preamble_is_stable() -> None:
    assert preamble() == preamble()


# --- what the page does ----------------------------------------------------


def test_nobody_is_put_into_fullscreen(granted: dict) -> None:
    # Loaded, the gate pressed, thirty frames played - and not one request.
    assert granted["callsBeforeAnyPress"] == []
    assert granted["untouched"]["asked"] == 0


def test_one_press_asks_once_for_the_wrapper(granted: dict) -> None:
    asks = [call for call in granted["calls"] if call["call"] == "request"]
    assert asks == [{"call": "request", "on": WRAP_ID}]


def test_the_button_becomes_the_way_back(granted: dict) -> None:
    assert granted["afterPress"]["label"] == LABEL_EXIT
    assert granted["afterPress"]["pressed"] == "true"
    assert not granted["afterSecond"]["active"]
    assert granted["afterSecond"]["label"] == LABEL_ENTER
    assert granted["afterSecond"]["pressed"] == "false"
    assert [c["call"] for c in granted["calls"] if c["call"] == "exit"] == ["exit"]


def test_the_lock_is_only_attempted_from_inside(granted: dict, refused: dict) -> None:
    assert [c["on"] for c in granted["calls"] if c["call"] == "lock"] == [LOCK_TO]
    # The request was refused, so there is no fullscreen to lock inside of.
    assert refused["settled"]["locks"] == 0


@pytest.mark.parametrize("kwargs", [{}, {"grant": False}, {"supported": False}, {"locks": True}])
def test_no_refusal_ever_escapes(kwargs: dict) -> None:
    # The half a written-but-bypassed .catch would fail: node's own
    # unhandled-rejection channel, not the page's word for it.
    assert _drive(**kwargs)["escaped"] == []


def test_the_page_counts_the_refusals_it_caught(refused: dict) -> None:
    # Two requests were made and both were declined. The control is
    # test_nothing_is_refused_when_nothing_refuses: without it, this number
    # could be a counter that only ever goes up.
    assert refused["settled"]["refused"] == 2
    assert not refused["afterPress"]["active"]
    assert refused["afterPress"]["label"] == LABEL_ENTER


def test_nothing_is_refused_when_nothing_refuses() -> None:
    assert _drive(locks=True)["settled"]["refused"] == 0


def test_an_unsupported_browser_is_offered_nothing(granted: dict) -> None:
    absent = _drive(supported=False)
    assert absent["atLoad"]["shown"] is False
    # ...and pressing it anyway calls nothing at all.
    assert absent["calls"] == []
    assert granted["atLoad"]["shown"] is True


def test_the_button_hands_keyboard_focus_back(granted: dict) -> None:
    # SPACE is 「撃つ」 in four of these templates. A button that kept focus
    # would turn the fire key into a fullscreen toggle.
    assert granted["blurred"] >= 1
