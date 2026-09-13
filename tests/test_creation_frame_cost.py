"""1 フレームがどれだけ描いてよいか (§32, C-1752).

Every judge in this repository reads what the page paints. None asked how
much. §32 settles where the number comes from: RAIL puts an animation
frame at **10ms of the application's own work** - the 16ms a 60fps frame
allows, less the ~6ms a browser spends rendering it.

That is a time, and the recording context this suite drives cannot
measure time. It counts calls; what a call costs is the device's
business. So no threshold is invented: what is recorded is what each
template drew on the day it was measured, and what is refused is a change
that quietly makes it much heavier.

The measurement is worth keeping in view on its own. The spread across
ten templates is twentyfold - catch 21, adventure 530 - which is not a
fault. It was simply nobody's knowledge.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.framecost import (
    FRAME_MEDIAN,
    FRAME_SLACK,
    count_probe,
    frame_ceiling,
)
from sidra_ai.creation.games import TEMPLATES, generate_game

#: Driven here rather than across all ten: the collector holds the whole
#: census, and this file pins the cheapest, the dearest and one between.
SAMPLE = ("catch", "puzzle", "adventure")


def _median(template: str, frames: int = 1200) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the frames")
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S)
    assert body is not None
    probe = subprocess.run(
        ["node", "-"],
        input=count_probe(body.group(1), frames=frames),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_table_covers_every_template() -> None:
    """A template missing from the table has no ceiling at all."""

    assert sorted(FRAME_MEDIAN) == sorted(TEMPLATES)


def test_the_slack_is_a_fifth_not_a_licence() -> None:
    assert 1.0 < FRAME_SLACK <= 1.5, FRAME_SLACK
    for template, median in FRAME_MEDIAN.items():
        assert frame_ceiling(template) > median, template


@pytest.mark.parametrize("template", SAMPLE)
def test_a_frame_stays_under_its_ceiling(template: str) -> None:
    seen = _median(template)
    assert seen["frames"] >= 500, seen
    assert seen["median"] <= frame_ceiling(template), (seen, frame_ceiling(template))


@pytest.mark.parametrize("template", SAMPLE)
def test_the_ceiling_is_still_about_this_page(template: str) -> None:
    """Without this, a ceiling of a hundred thousand is green forever."""

    seen = _median(template)
    assert seen["median"] * 2 >= FRAME_MEDIAN[template], (
        seen["median"],
        FRAME_MEDIAN[template],
    )


def test_the_counter_sees_a_call_nobody_listed() -> None:
    """The context is a Proxy, not a list of methods we thought of.

    A template reaching for something unlisted would otherwise draw for
    free, which is the shape of every census that enumerates instead of
    intercepting.
    """

    source = count_probe("const c=document.getElementById('x').getContext('2d');"
                         "let n=0;requestAnimationFrame(function f(){"
                         "c.somethingNobodyListed();c.fillRect(0,0,1,1);"
                         "if(++n<5)requestAnimationFrame(f)});", frames=6)
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=120
    )
    assert probe.returncode == 0, probe.stderr[:400]
    seen = json.loads(probe.stdout.strip().splitlines()[-1])
    assert seen["median"] == 2, seen


def test_frames_that_drew_nothing_are_not_counted() -> None:
    """A title screen is allowed to be cheap; it is not a frame this is about."""

    source = count_probe("let n=0;requestAnimationFrame(function f(){"
                         "if(++n<8)requestAnimationFrame(f)});", frames=9)
    probe = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=120
    )
    assert probe.returncode == 0, probe.stderr[:400]
    assert json.loads(probe.stdout.strip().splitlines()[-1])["frames"] == 0
