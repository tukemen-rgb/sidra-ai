"""The puzzle, played to its end rather than merely generated.

A board that never ends, or one that congratulates a stuck player, is a page
that opens and runs. So the strongest test here drives the real script in
node until no move remains, and checks that the ending it reports is the one
that happened: "solved" and "no moves left" are different outcomes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.animation import LOOP_PROBE
from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.games import (
    TEMPLATES,
    choose_template,
    detect_genre,
    generate_game,
    validate_game_html,
)
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.touchpad import unreachable_keys

#: Take every legal move there is, in reading order, until none is left.
_PLAY_IT_OUT = """
let moves = 0;
while (state === 'play' && moves < 400) {
  let done = false;
  for (let y = 0; y < ROWS && !done; y++) { for (let x = 0; x < COLS && !done; x++) {
    if (grid[y][x] >= 0 && group(x, y).length > 1) { cur = {x: x, y: y}; pop(); moves++; done = true }
  } }
  if (!done) break;
}
console.log(JSON.stringify({ state: state, moves: moves, score: score,
  cleared: cleared, leftover: grid.flat().filter(v => v >= 0).length }));
"""


def _playthrough(request: str = "パズルゲームを作って") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - node is present here
        pytest.skip("node is needed to play the board out")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    harness = (
        LOOP_PROBE.replace("REDUCED_INPUT", "false")
        .replace("FRAMES_INPUT", "2")
        .replace("SCRIPT_PLACEHOLDER", script.group(1))
        .split("console.log")[0]
        + _PLAY_IT_OUT
    )
    finished = subprocess.run(
        ["node", "-"], input=harness, capture_output=True, text=True, timeout=60
    )
    assert finished.returncode == 0, finished.stderr[:400]
    return json.loads(finished.stdout)


def test_a_puzzle_request_reaches_the_puzzle():
    for text in ("パズルゲームを作って", "さめがめ作って", "puzzle game を作って"):
        assert choose_template(text) == "puzzle", text


def test_the_last_apology_retired_itself():
    genre = detect_genre("パズルゲームを作って")

    assert genre is not None
    assert genre.template == "puzzle"
    assert genre.supported is True


def test_the_summary_no_longer_apologises_for_puzzles(tmp_path):
    message = "パズルゲームを作って"

    outcome = build_game_generator(tmp_path)(message, detect_creation_intent(message))

    assert outcome.details["built_template"] == "puzzle"
    assert outcome.details["genre_substituted"] is False
    assert "まだ作れない" not in outcome.summary


def test_the_board_runs_out_of_moves_and_says_which_ending_it_was():
    result = _playthrough()

    assert result["state"] == "over"
    assert result["moves"] > 0
    # Whatever happened, the flag has to match the board rather than the mood.
    assert result["cleared"] is (result["leftover"] == 0)


def test_bigger_groups_are_worth_more_than_the_same_cells_taken_apart():
    # Squared scoring is the only reason to look for the large group rather
    # than the nearest one; without it the puzzle is a clicker.
    page = generate_game("パズルゲームを作って").html

    assert "cells.length*cells.length" in page


def test_the_page_runs_and_carries_the_shared_preambles():
    page = generate_game("パズルゲームを作って").html

    assert validate_game_html(page)["playable"]
    for wired in ("sfx(", "shake(", "hitstop(", "burst(", "drawPad"):
        assert wired in page, wired


def test_colours_are_not_the_only_way_to_tell_the_pieces_apart():
    # C-1018's rule, and it matters most here: the whole game is matching.
    page = generate_game("パズルゲームを作って").html

    assert "for(let i=0;i<=v;i++)" in page


def test_every_key_the_puzzle_reads_has_a_pad_button():
    assert unreachable_keys(TEMPLATES["puzzle"].script) == set()


def test_difficulty_changes_the_board_rather_than_the_wording():
    easy = generate_game("簡単なパズルゲームを作って").html
    hard = generate_game("難しいパズルゲームを作って").html

    grab = lambda page: re.search(  # noqa: E731
        r"COLOURS=tuneNum\('speed',(\d+)\),COLS=tuneNum\('band',(\d+)\)", page
    ).groups()
    assert grab(easy) != grab(hard)


def _flown(*, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    from sidra_ai.creation.puzzle import probe_source

    page = generate_game("パズルゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_collapse_is_an_ease_and_not_a_teleport():
    """§1 トゥイーン: the fall is seen. Popped and watched on the running page.

    Right after the pop the board is away from rest, mid-flight it has
    moved back but not arrived (an ease, not a delayed snap), and by the
    end it is exactly at rest.
    """

    facts = _flown()

    assert facts["hadTarget"], "the board offered a group with a tile above it"
    assert facts["scoreAfter"] > facts["scoreBefore"], "the measured pop happened"
    assert facts["movingAtPop"] > 0
    assert 0 < facts["movingMid"] < facts["movingAtPop"]
    assert facts["movingSettled"] == 0


def test_reduced_motion_keeps_the_snap():
    """The tween is decoration: under reduced motion the board never moves."""

    facts = _flown(reduced=True)

    assert facts["scoreAfter"] > facts["scoreBefore"], "the game itself still works"
    assert facts["movingAtPop"] == 0
    assert facts["movingMid"] == 0
