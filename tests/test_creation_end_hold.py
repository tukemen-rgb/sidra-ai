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


def test_the_clock_ending_is_fully_quiet_first(clock_end: dict) -> None:
    assert clock_end["broke"]
    assert not clock_end["early"]["strip"], "the strip lands on the verdict's frame"
    assert not clock_end["early"]["ask"], "the banner asks before the quiet ends"
    assert clock_end["late"]["strip"], "the strip never arrives"


def test_the_template_ending_still_holds_the_shared_strip(template_end: dict) -> None:
    assert template_end["broke"]
    assert not template_end["early"]["strip"]
    assert template_end["late"]["strip"]


@pytest.mark.parametrize("who", ["clock_end", "template_end"])
def test_the_quiet_never_loses_the_record(who: str, request) -> None:
    got = request.getfixturevalue(who)
    assert got["early"]["banked"], "the bank waited with the chrome"
    assert got["early"]["bestKept"], "the best was not written inside the quiet"
