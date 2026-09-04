"""C-1129: the walk bounces off the ends of the scale instead of sticking.

The melody is a random walk over ten pentatonic degrees, and it used to
end at ``Math.max(0, Math.min(9, ...))``. A clamp is not a boundary, it is
an absorber: a step that reached past an end became no step at all, so a
run of outward draws printed one pitch for bars. These tests drive the
real generated page and read the walk the page itself recorded - checking
the melody by re-running the melody generator would only prove the check
agrees with itself.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.music import probe_source

#: Ten different requests are ten different seeds, which is what it takes
#: to reach an end at all - a single tune may never lean on one.
REQUESTS = (
    "ゲームを作って",
    "パズルゲームを作って",
    "釣りゲームを作って",
    "レースゲームを作って",
    "シューティングゲームを作って",
    "キャッチゲームを作って",
    "迷路のゲームを作って",
    "怪獣のゲームを作って",
)


def _heard(request: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    script = re.search(r"<script>(.*?)</script>", generate_game(request).html, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def walks() -> list[tuple[str, dict]]:
    return [(request, _heard(request)) for request in REQUESTS]


def test_the_log_is_the_tune_that_played(walks):
    # Without this the walk could be a story told beside the melody, and
    # every other test here would be checking the story.
    for request, heard in walks:
        sounded = [note for note in heard["mel"] if note >= 0]
        assert [entry[2] for entry in heard["walk"]] == sounded, request


def test_the_walk_stays_on_the_scale(walks):
    for request, heard in walks:
        for _, _, went in heard["walk"]:
            assert 0 <= went <= 9, request


def test_every_step_is_the_size_it_drew(walks):
    # The defect in one line: a clamp shortens the step it was given. At
    # an end or in the middle, the distance moved is the distance drawn.
    for request, heard in walks:
        for came, drawn, went in heard["walk"]:
            assert abs(went - came) == abs(drawn), (request, came, drawn, went)


def test_an_end_never_holds_a_note(walks):
    for request, heard in walks:
        for came, drawn, went in heard["walk"]:
            if drawn != 0:
                assert went != came, (request, came, drawn)


def test_the_ends_are_actually_reached(walks):
    # A boundary rule checked only on tunes that never approach a boundary
    # proves nothing. This is the guard that keeps the rest honest.
    bounces = sum(
        1
        for _, heard in walks
        for came, drawn, _ in heard["walk"]
        if not 0 <= came + drawn <= 9
    )
    assert bounces > 0


def test_a_repeated_note_is_always_a_zero_draw(walks):
    # What "no drone" means exactly: the longest run of one pitch is the
    # longest chain of zero draws, and nothing else can make one.
    for request, heard in walks:
        walk = heard["walk"]
        for index in range(1, len(walk)):
            if walk[index][2] == walk[index - 1][2]:
                assert walk[index][1] == 0, (request, index, walk[index])


def test_the_same_request_walks_the_same_way():
    # The seed still owns the tune - the fix changed the rule, not the
    # determinism the docstring promises.
    first, second = _heard("釣りゲームを作って"), _heard("釣りゲームを作って")
    assert first["walk"] == second["walk"]
    assert first["mel"] == second["mel"]
