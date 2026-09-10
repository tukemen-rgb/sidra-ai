"""The ending gets a quiet beat before the chrome (§6 観察 8, C-1382).

The strip used to land on the very frame the round broke: two bars of
「R でもう一度」 over a fanfare still on its first note. Now the verdict
lands at once, the shared chrome waits 45 frames (the fanfare is ~30),
and the bank moves to the ending's FIRST frame so an R pressed inside
the quiet still keeps the record.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.round import hold_probe_source


def _drive(request: str, template: str | None = None) -> dict:
    if template:
        html = generate_game(request, template=template).html
    else:
        html = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"], input=hold_probe_source(script),
        capture_output=True, text=True, timeout=300,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def clock_end() -> dict:
    return _drive("釣りゲームを作って")


@pytest.fixture(scope="module")
def template_end() -> dict:
    return _drive("ゲームを作って", template="marble")


@pytest.fixture(scope="module")
def death_end() -> dict:
    return _drive("シューティングゲームを作って")


def test_the_clock_ending_is_fully_quiet_first(clock_end: dict) -> None:
    assert clock_end["broke"]
    assert not clock_end["early"]["strip"], "the strip lands on the verdict's frame"
    assert not clock_end["early"]["ask"], "the banner asks before the quiet ends"
    assert clock_end["late"]["strip"], "the strip never arrives"


def test_the_template_ending_is_fully_quiet_too(template_end: dict) -> None:
    """C-1384: the template's own 「もう一度」 line waits with the chrome."""

    assert template_end["broke"]
    assert not template_end["early"]["strip"]
    assert not template_end["early"]["ask"], "the verdict screen asks at once"
    assert template_end["late"]["strip"] and template_end["late"]["ask"]


def test_the_death_ending_is_fully_quiet_too(death_end: dict) -> None:
    assert death_end["broke"]
    assert not death_end["early"]["strip"]
    assert not death_end["early"]["ask"]
    assert death_end["late"]["strip"] and death_end["late"]["ask"]


@pytest.mark.parametrize("who", ["clock_end", "template_end", "death_end"])
def test_the_quiet_never_loses_the_record(who: str, request) -> None:
    got = request.getfixturevalue(who)
    assert got["early"]["banked"], "the bank waited with the chrome"
    assert got["early"]["bestKept"], "the best was not written inside the quiet"


# --------------------------------------------- every ending, not just three


#: The same probe drives whatever page it is handed until the round breaks,
#: so measuring three of the ten was a choice nobody had revisited (C-1637).
_ENDINGS = {
    "catch": ("フルーツキャッチを作って", None),
    "racing": ("レースゲームを作って", None),
    "platformer": ("ジャンプで進むゲームを作って", None),
    "puzzle": ("パズルゲームを作って", None),
    "adventure": ("迷宮を冒険するゲームを作って", None),
    "duel": ("光線で撃ち合う対戦ゲームを作って", None),
    "kaiju": ("巨大怪獣と戦うゲームを作って", "kaiju"),
}


@pytest.mark.parametrize("template", sorted(_ENDINGS))
def test_every_other_ending_holds_its_quiet_too(template: str) -> None:
    request, kind = _ENDINGS[template]
    seen = _drive(request, kind)

    assert seen["broke"], f"{template} never reached an ending"
    assert not seen["early"]["strip"], "the shared strip arrives in the quiet"
    assert not seen["early"]["ask"], "an invitation arrives in the quiet"
    assert seen["late"]["strip"] and seen["late"]["ask"], "the chrome never arrives"


def test_the_probe_runs_on_the_maze_at_all() -> None:
    """It could not, until C-1637. ``HOLD_PROBE`` declared ``let guard``
    and adventure's page calls its guardian ``guard``, so the whole probe
    was a ``SyntaxError`` - one template of ten was unmeasurable, and the
    reading that hid behind it was not a failing check but no check.
    """

    seen = _drive("迷宮を冒険するゲームを作って")

    assert seen["broke"]


def test_the_duel_verdict_does_not_invite_while_it_is_still_quiet() -> None:
    """It used to read 「敗北。もう一度。」 - the invitation the gated line
    below it waits 45 frames to give, said on the ending's first frame."""

    seen = _drive("光線で撃ち合う対戦ゲームを作って")

    assert not seen["early"]["ask"]
    assert seen["late"]["ask"]


def test_no_shared_round_probe_takes_a_word_a_page_uses() -> None:
    """The shape of C-1637's second half, caught at the source: a probe's
    own top-level ``let`` has to stay out of the names the templates own.
    ``guard`` is adventure's guardian; the two probes that declared it are
    renamed, and this keeps them that way.
    """

    import pathlib

    import sidra_ai.creation.round as module

    text = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    taken = [
        f"{n}: {line.strip()}"
        for n, line in enumerate(text.splitlines(), 1)
        if re.search(r"^\s*(let|const|var)\s+(guard|hero|boss|me|state)\b", line)
    ]

    assert taken == [], "\n".join(taken)
