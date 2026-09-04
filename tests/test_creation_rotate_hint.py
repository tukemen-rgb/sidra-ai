"""C-1415: the one line a phone held upright gets, and nobody else.

§18: the canvas keeps its 720:320 ratio at every page width, so the same
phone plays at about half the size on each side upright that it gives lying
down, and the page never mentioned it.

What these tests pin that the judge does not: the judge asks whether the
behaviour is right on a page that was generated correctly. These ask
whether the *page* is right - that the sentence is really in the document
and says something, that it is off until the script turns it on (so a page
whose script never ran shows nothing rather than nagging a desktop reader),
and that the hint is a hint: nothing about it is in the way of the game.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.rotate import (
    ROTATE_ID,
    ROTATE_QUERIES,
    ROTATE_TEXT,
    preamble,
    probe_source,
)


def _page(template: str = "racing") -> str:
    return generate_game("ゲームを作って", template=template).html


def _script(page: str) -> str:
    body = re.search(r"<script>(.*?)</script>", page, re.S)
    assert body is not None
    return body.group(1)


def _turn(**kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to turn the screen")
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
def upright() -> dict:
    return _turn(portrait=True, coarse=True, press=True)


# --- what is in the page ---------------------------------------------------


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_page_carries_the_sentence_once(template: str) -> None:
    page = _page(template)
    assert page.count(f'id="{ROTATE_ID}"') == 1
    assert page.count(ROTATE_TEXT) == 1


def test_the_sentence_promises_no_number() -> None:
    # The gain depends on the device's own aspect ratio. A page that says
    # 「2 倍」 on a screen where it is 1.4 has told the reader something
    # false to sound more convincing.
    assert not re.search(r"\d", ROTATE_TEXT)


def test_the_stylesheet_only_ever_hides_it() -> None:
    """One mechanism decides one element.

    The stylesheet's job is the starting state; the script owns the rest,
    because rule 3 ("not once play has started") is not a media condition
    and cannot be written as one.
    """

    page = _page()
    rules = re.findall(r"\.rotatehint\{[^}]*\}", page)
    assert rules, "the class the paragraph carries is not styled at all"
    assert all("display:none" in rule for rule in rules)
    assert "@media (orientation" not in page


def test_no_rotate_token_survives_into_a_page() -> None:
    body = _script(_page())
    assert "ROTATE_ID_TOKEN" not in body
    assert "ROTATE_QUERIES_TOKEN" not in body
    for query in ROTATE_QUERIES:
        assert query in body


def test_the_preamble_is_stable() -> None:
    assert preamble() == preamble()


# --- what the page does ----------------------------------------------------


def test_a_phone_held_upright_is_told(upright: dict) -> None:
    assert upright["atLoad"]["shown"] is True
    assert upright["atLoad"]["display"] == "block"


def test_turning_the_phone_answers_immediately(upright: dict) -> None:
    # No reload: the queries are subscribed to, so the sentence follows the
    # screen the way a stylesheet rule would have.
    assert upright["afterTurn"]["shown"] is False
    assert upright["turnedBack"]["shown"] is True


def test_a_phone_opened_sideways_is_told_nothing_until_it_is_turned() -> None:
    flat = _turn(portrait=False, coarse=True)
    assert flat["atLoad"]["shown"] is False
    assert flat["afterTurn"]["shown"] is True


@pytest.mark.parametrize("portrait", [True, False])
def test_a_mouse_driven_window_is_never_told_to_rotate(portrait: bool) -> None:
    # A tall desktop window is portrait too, and telling somebody to turn
    # their monitor is the page not knowing what it is running on.
    seen = _turn(portrait=portrait, coarse=False)
    assert seen["atLoad"]["shown"] is False
    assert seen["afterTurn"]["shown"] is False


def test_the_line_leaves_when_the_game_starts(upright: dict) -> None:
    assert upright["afterStart"]["present"] is False
    assert upright["inBody"] == 0
    # ...and turning the phone during play does not bring it back.
    assert upright["afterStart"]["afterTurningBack"]["shown"] is False


def test_it_is_a_hint_and_not_a_gate(upright: dict) -> None:
    # The press still started the game, with the sentence on screen.
    assert upright["gate"]["state"] == "playing"
    assert upright["gate"]["frames"] >= 1
