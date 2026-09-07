"""A mash carried through the buzzer must not erase the result (C-1472).

Restarting this clock's round is a real ``location.reload()``. A player who
was still pressing R when the sixty seconds ran out therefore did not skip
the result screen - they destroyed it, on the frame after the buzzer, having
never seen 「ここまで」, the reason line, or their own record.

The fix is a short shield: for ``ROUND_SHIELD_FRAMES`` after the buzzer, R
and a tap are not counted as a restart. What makes that a fix rather than a
delay is the other half, and both halves are read off a real generated page
driven in node:

* while the shield is up, no reload happens no matter how hard the page is
  mashed;
* the moment it is down, one press reloads exactly as it always did.

The frame index of the mash loop is deliberately NOT what these assert on.
The probe's ``requestAnimationFrame`` holds a single callback, so the round's
wrapper loses a few early turns to the other schedulers on the page - a
property of the harness, not of the product. Every assertion is keyed to
``shielded``, which is the flag the page itself decides on.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.round import ROUND_SHIELD_FRAMES, shield_probe_source

#: Templates whose go is ended by the clock rather than by themselves, so the
#: buzzer path is the one under test.
REACHES_THE_BUZZER = ("catch", "fishing", "platformer")

#: Both ways in. A shield over the keyboard that left the canvas open would
#: pass a key-only probe and fail every player on a phone.
MASHES = ("key", "tap")


def drive(template: str, *, mash: str = "key", **kw):
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    done = subprocess.run(
        ["node", "-"],
        input=shield_probe_source(body, mash=mash, **kw),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-600:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def runs():
    return {
        (template, mash): drive(template, mash=mash)
        for template in REACHES_THE_BUZZER
        for mash in MASHES
    }


# ------------------------------------------------------------- the shield


@pytest.mark.parametrize("template", REACHES_THE_BUZZER)
@pytest.mark.parametrize("mash", MASHES)
def test_no_reload_happens_while_the_shield_is_up(runs, template, mash) -> None:
    run = runs[(template, mash)]
    assert run["buzzerAt"] is not None, "the clock never fired"
    assert run["atBuzzer"] == 0, "reloaded before the mash even started"
    shielded = [f for f in run["mash"] if f["shielded"]]
    assert shielded, "the shield was never up"
    assert all(f["reloads"] == 0 for f in shielded), [
        f for f in shielded if f["reloads"]
    ]


@pytest.mark.parametrize("template", REACHES_THE_BUZZER)
@pytest.mark.parametrize("mash", MASHES)
def test_the_press_after_the_shield_still_restarts_at_once(
    runs, template, mash
) -> None:
    """The other half: the shield must not become a wait.

    Without this, a build that simply refused to restart at all would pass
    every "no reload" assertion above.
    """

    run = runs[(template, mash)]
    down = [f for f in run["mash"] if not f["shielded"]]
    assert down, "the shield never came down inside the mash"
    assert run["reloadsAfterMash"] > 0


@pytest.mark.parametrize("template", REACHES_THE_BUZZER)
@pytest.mark.parametrize("mash", MASHES)
def test_the_first_reload_lands_on_the_first_unshielded_press(
    runs, template, mash
) -> None:
    """Not one frame later than it has to be - the shield adds no friction."""

    run = runs[(template, mash)]
    first_down = next(
        f["frame"] for f in run["mash"] if not f["shielded"]
    )
    assert run["firstReloadAt"] == first_down


@pytest.mark.parametrize("template", REACHES_THE_BUZZER)
def test_the_result_is_on_the_screen_the_shield_is_protecting(
    runs, template
) -> None:
    """A shield over a blank screen would be protecting nothing."""

    assert "ここまで" in runs[(template, "key")]["said"]


def test_the_shield_is_shorter_than_the_quiet_beat() -> None:
    """It has to expire before 「R / タップでもう一度」 appears.

    A shield outlasting the prompt would be telling the player to press and
    then ignoring the press - worse than the bug it fixes.
    """

    run = drive("catch")
    assert run["shield"] == ROUND_SHIELD_FRAMES
    assert run["shield"] < run["hold"]


# ------------------------------------------------------------- the break


def test_removing_the_shield_puts_the_bug_back(tmp_path) -> None:
    """The both-directions check, run rather than asserted.

    The page is regenerated with the shield's frame budget set to zero and
    driven exactly as above. If the mash still failed to reload, everything
    above would be measuring something other than the shield.
    """

    page = generate_game("ゲームを作って", template="catch").html
    body = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    broken = body.replace(
        f"const ROUND_SHIELD={ROUND_SHIELD_FRAMES};", "const ROUND_SHIELD=-1;"
    )
    assert broken != body, "the shield constant is not where the test thinks"
    done = subprocess.run(
        ["node", "-"],
        input=shield_probe_source(broken, mash="key"),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-600:]
    run = json.loads(done.stdout.strip().splitlines()[-1])
    assert run["firstReloadAt"] == 0, "the mash no longer reloads on frame 0"
    assert not any(f["shielded"] for f in run["mash"])


# ------------------------------------------------- scope: only this buzzer


#: Templates that finish before the clock can reach them. Their R and their
#: tap belong to their own end screen, and the item scopes this change out of
#: them explicitly.
ENDS_BY_ITSELF = ("duel", "marble", "shooter")


@pytest.mark.parametrize("template", ENDS_BY_ITSELF)
def test_a_template_that_ends_by_itself_never_spends_the_shield(template) -> None:
    """Its own ending owns its own R - this change must not reach it.

    ``roundShielded`` is gated on ``ROUND_DONE``, which only the clock sets,
    so a game that finished on its own leaves the counter at zero however
    long its end screen is up. Asserted, not skipped: a scope claim nobody
    checks is a scope claim nobody kept.
    """

    run = drive(template)
    assert run["buzzerAt"] is None, "the clock fired - wrong template for this"
    assert run["doneAtStop"] is False
    assert all(f["shieldFrames"] == 0 for f in run["mash"])
    assert not any(f["shielded"] for f in run["mash"])
