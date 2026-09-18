"""A line the page said can be read back after its timer (§30 事実 1, C-1776).

``test_creation_say_readable`` already claims every message stays up long
enough to read at four characters a second. §30 事実 1 asks for the thing a
frame count cannot give - 「Allow players to progress through text prompts
at their own pace」 (gameaccessibilityguidelines.com, recorded in
``docs/research/game-design-notes.md`` §30) - the reader's pace, not a good
guess at it.

The census behind this file: ``say()`` exists in two of the ten templates,
and most of what it says survives its own timer anyway, because the line
repeats when the action does (touch the locked chest again and it says so
again) and the standing facts - gems, key, charm, room - are on the HUD,
which never expires. One line is neither. Adventure's stone names the knock
order for THIS run, ``KORDER`` being shuffled per seed, so no briefing can
carry it; the stone stands in the forest and the three marks it speaks of
are in the cave, and crossing between the two rooms says the room's name,
which overwrites the order before it can be used. Re-reading it is a walk
back through the roamers. That is a line whose reading speed costs hearts.

Everything here is driven: the page's own ``say()`` with the page's own
literal, the page's own ``msgT`` run to zero, the words proved gone from the
playing screen, and only then P. "Readable on pause" must not be satisfiable
by the message simply still being up.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.canvaswords import said_lines
from sidra_ai.creation.games import TEMPLATES
from sidra_ai.creation.startscreen import PREAMBLE_NAMES, reread_probe_source

#: The two that speak. Written down rather than discovered, so a template
#: that gains a voice - or loses one - is a test failure and a decision,
#: not a silently smaller claim.
SPEAKING = ("adventure", "platformer")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="the probe needs node"
)


def _script(template: str) -> str:
    html = generate_game("ゲームを作って", template=template).html
    return re.search(r"<script>(.*?)</script>", html, re.S).group(1)


def _literals(script: str) -> list[str]:
    # Through the table as well as the literals: since C-1960 a template
    # says say(CW.lamp_lit), and a census that only saw literals would
    # report a speaking template as mute (which is how this file's
    # measurements would quietly become measurements of nothing).
    return sorted(set(said_lines(script)), key=len, reverse=True)


def _probe(script: str) -> dict:
    lits = _literals(script)
    run = subprocess.run(
        ["node", "-"],
        input=reread_probe_source(script, line=lits[0], lines=tuple(lits[:3])),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert run.returncode == 0, run.stderr[-600:]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def probed() -> dict[str, dict]:
    return {key: _probe(_script(key)) for key in SPEAKING}


def test_exactly_these_templates_speak() -> None:
    spoke = tuple(k for k in sorted(TEMPLATES) if _literals(_script(k)))
    assert spoke == SPEAKING, (
        "the set of templates with a voice changed; the drawer's claim, "
        "and this file's census, are about that set"
    )


@pytest.mark.parametrize("template", SPEAKING)
def test_the_line_really_leaves_the_playing_screen(
    template: str, probed: dict[str, dict]
) -> None:
    """The premise. Without it, "readable on pause" measures nothing."""

    got = probed[template]
    assert got["upWhileTiming"], "the line was never drawn at all"
    assert got["expired"], "the page's own msgT never reached zero"
    assert not got["upAfterExpiry"], "the line was still on the screen"


@pytest.mark.parametrize("template", SPEAKING)
def test_the_line_comes_back_on_pause(
    template: str, probed: dict[str, dict]
) -> None:
    got = probed[template]
    assert got["gate"] == "paused" and got["pauseHeading"]
    assert got["onPause"], "an expired line cannot be read back anywhere"


@pytest.mark.parametrize("template", SPEAKING)
def test_the_drawer_belongs_to_the_paused_screen(
    template: str, probed: dict[str, dict]
) -> None:
    """Resumed, the game gets its screen back: the drawer is a place to
    read, not an overlay to play under."""

    assert not probed[template]["onResumed"]


@pytest.mark.parametrize("template", SPEAKING)
def test_the_drawer_shows_every_line_it_holds(
    template: str, probed: dict[str, dict]
) -> None:
    """A log with hidden entries lies about what it kept."""

    got = probed[template]
    assert got["fullKept"] > 0
    assert got["fullShown"] == got["fullKept"], (
        f"{got['fullShown']} of {got['fullKept']} kept lines reached the screen"
    )


@pytest.mark.parametrize("template", SPEAKING)
def test_the_cap_drops_the_oldest_and_keeps_the_newest(
    template: str, probed: dict[str, dict]
) -> None:
    got = probed[template]
    assert got["keep"] == 3, "three is what the stone-to-marks walk needs"
    assert got["capHolds"] and got["oldestDropped"] and got["newestHeld"]


@pytest.mark.parametrize("template", SPEAKING)
def test_a_repeated_line_is_one_line(
    template: str, probed: dict[str, dict]
) -> None:
    """Two hearts lost in a row must not push the stone out of a
    three-line drawer."""

    assert probed[template]["repeatsCollapse"]


@pytest.mark.parametrize("template", SPEAKING)
def test_the_demos_words_are_not_the_players(
    template: str, probed: dict[str, dict]
) -> None:
    """C-1401's rule, for words: the attract loop plays behind the title
    and both of these templates speak while it does."""

    got = probed[template]
    assert got["demoSaid"] > 0, (
        "the demo said nothing, so forgetting it is a claim about nothing"
    )
    assert got["forgotDemo"], f"{got['demoSaid']} of the demo's lines survived"


@pytest.mark.parametrize("template", SPEAKING)
def test_the_drawer_sits_between_the_briefing_and_the_way_out(
    template: str, probed: dict[str, dict]
) -> None:
    """Both blocks are on one 320px canvas. Measured from the y each row
    was actually drawn at, because a list of strings cannot say whether
    two blocks were written over each other."""

    got = probed[template]
    assert got["belowBrief"], "the drawer overlaps the three briefing lines"
    assert got["aboveExit"], "the drawer runs past the 「つづける」 line"
    assert got["exitShown"], "the way out was not drawn"


@pytest.mark.parametrize("template", SPEAKING)
def test_an_overlong_line_is_cut_rather_than_run_past_the_exit(
    template: str, probed: dict[str, dict]
) -> None:
    """No page literal is long enough to reach the drawer's stop, which is
    exactly why it is driven with words that are: a guard nothing reaches
    is a guard nobody has checked."""

    got = probed[template]
    assert got["longWanted"] > got["longDrawn"] > 0
    assert got["longClipped"]
    assert got["longAboveExit"], "a cut drawer still wrote past the way out"
    assert got["longExitShown"]


def test_the_drawer_is_the_gates_and_no_template_has_its_own() -> None:
    """Same contract the briefing table keeps: one definition, in the
    preamble, so two screens cannot drift apart."""

    for name in ("gateSaid", "gateSaidLines", "gateSaidForget", "gateSaidTable"):
        assert name in PREAMBLE_NAMES
    page = generate_game("ゲームを作って", template="adventure").html
    assert page.count("function gateSaidTable") == 1
    assert not any(
        "function gateSaid" in spec.script for spec in TEMPLATES.values()
    )


@pytest.mark.parametrize("template", SPEAKING)
def test_say_feeds_the_drawer_without_depending_on_it(
    template: str
) -> None:
    """The gate is prepended to every page, but these templates' own
    probes run their script alone - so say() must survive a missing
    drawer rather than throw inside the game loop."""

    script = _script(template)
    assert "typeof gateSaid==='function'" in script
