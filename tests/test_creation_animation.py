"""The page moves, and it stops moving for a viewer who asked it to.

`prefers-reduced-motion` is a requirement here rather than a nicety: someone
who set it did so because motion makes them ill. So these tests run the
helpers rather than reading them, and they check both directions - a page
that never animates would satisfy "stops when asked" while failing at the
thing it was asked to do.

The other property, easy to lose in a later edit: reduced motion stops the
*decorative* movement and leaves the game running. Freezing the game loop
would honour the setting and break the artifact.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.animation import (
    PREAMBLE,
    PREAMBLE_NAMES,
    loop_probe,
    probe_source,
    with_animation,
)
from sidra_ai.creation.games import TEMPLATES, generate_game, validate_game_html

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="the animation probe runs the helpers in node; nothing to run without it",
)


def _run(*, reduced: bool) -> dict:
    finished = subprocess.run(
        ["node", "-"],
        input=probe_source(reduced=reduced),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert finished.returncode == 0, finished.stderr
    return json.loads(finished.stdout)


def test_decorative_frames_advance_normally() -> None:
    """The half that a page doing nothing would fail."""

    assert _run(reduced=False)["distinctFrames"] > 1


def test_decorative_frames_freeze_under_reduced_motion() -> None:
    assert _run(reduced=True)["distinctFrames"] == 1


def test_easing_becomes_linear_under_reduced_motion() -> None:
    """Its endpoints stay put; only the curve between them flattens.

    An easing function that changed its endpoints would move things to the
    wrong place rather than move them differently.
    """

    moving, still = _run(reduced=False), _run(reduced=True)

    assert moving["easeMid"] != still["easeMid"]
    assert moving["easeStart"] == still["easeStart"] == 0
    assert moving["easeEnd"] == still["easeEnd"] == 1


def test_every_template_still_runs_with_the_preamble() -> None:
    """An animated page that stopped parsing is worse than a static one."""

    for key in TEMPLATES:
        verdict = validate_game_html(generate_game("ゲームを作って", template=key).html)
        assert verdict["playable"], (key, verdict["failures"])


def test_the_game_loop_is_not_what_gets_frozen() -> None:
    """Reduced motion must not stop the game itself.

    ``requestAnimationFrame`` keeps being called; it is ``FRAME`` that
    collapses to a constant. A template that gated its loop on ``REDUCED``
    would pass every other test here and hand a still image to the viewer
    who most needed the game to work.

    This used to be checked by forbidding ``if(REDUCED)return`` anywhere on
    the page. That reading stopped being true of the code rather than of the
    property: a *decorative* effect opting out of reduced motion is the
    setting working (C-1020's shake and particles do exactly that), and the
    string cannot tell that apart from a loop opting out. So the page is run
    instead, and the frames it manages are counted - which also catches a
    loop stalled for reasons no string would have named.
    """

    if shutil.which("node") is None:  # pragma: no cover - node is present here
        pytest.skip("node is needed to drive the loop")
    for key in TEMPLATES:
        page = generate_game("ゲームを作って", template=key).html
        assert "requestAnimationFrame" in page
        script = re.search(r"<script>(.*?)</script>", page, re.S)
        assert script is not None
        for reduced in (False, True):
            finished = subprocess.run(
                ["node", "-"],
                input=loop_probe(script.group(1), reduced=reduced, frames=40),
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert finished.returncode == 0, (key, finished.stderr[:400])
            result = json.loads(finished.stdout)
            assert result["reduced"] is reduced
            # Every frame handed back was asked for again: the loop is alive
            # for all forty, not just the first.
            assert result["ran"] == 40, (key, reduced, result)


def test_the_preamble_introduces_only_the_names_it_documents() -> None:
    """A name collision would break the page only once it is generated."""

    declared = {
        line.split("(")[0].removeprefix("function ").strip()
        for line in PREAMBLE.splitlines()
        if line.startswith("function ")
    }
    declared |= {
        line.split("=")[0].removeprefix("const ").strip()
        for line in PREAMBLE.splitlines()
        if line.startswith("const ")
    }

    assert declared == set(PREAMBLE_NAMES)


def test_with_animation_puts_the_preamble_first() -> None:
    combined = with_animation("const x = 1;")

    assert combined.startswith(PREAMBLE)
    assert combined.endswith("const x = 1;")
