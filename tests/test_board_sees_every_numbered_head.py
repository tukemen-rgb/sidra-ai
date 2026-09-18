"""C-1958: the board's instrument reads every number an item claims.

Exercises the real script, the way the eval does - these are the two halves
of the same check, so neither is asserted against a copy of the other's
expectations.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from sidra_ai.evals.board_sees_every_numbered_head import (
    _BOARD,
    _COLLIDING,
    evaluate_board_sees_every_numbered_head,
)

_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def board():
    spec = importlib.util.spec_from_file_location(
        "_board_for_tests", _ROOT / "scripts" / "check_backlog_board.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_side_is_right() -> None:
    result = evaluate_board_sees_every_numbered_head()
    assert result.sides_right == result.sides_total == 5, result.failures


import pytest as _pytest


@_pytest.mark.parametrize("number", ["C-8004", "C-8005"])
def test_an_unusually_written_head_still_names_its_item(board, number) -> None:
    # C-8004 is the labelled form; C-8005 is the bold-free one, found live on
    # the board while this was written (it was printing as 「L262」).
    ids = {item["id"] for item in board.read_items(_BOARD) if item["id"]}
    assert number in ids


def test_a_quoted_number_heads_nothing(board) -> None:
    # The shape the loose repair gets wrong. C-8009 appears only inside two
    # quotations - one in a claim that has its own number, one in a line that
    # has none at all. The second is the one with teeth: the first form finds
    # nothing there, so a loosened second form is what answers.
    ids = {item["id"] for item in board.read_items(_BOARD) if item["id"]}
    assert "C-8009" not in ids


def test_no_number_the_old_expression_read_has_moved(board) -> None:
    # Recomputed rather than remembered, on the real board.
    live = (_ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    for item in board.read_items(live):
        direct = board.HEADS.search(item["text"])
        if direct:
            assert item["id"] == direct.group(1), item["line"]


def test_an_undecided_repeat_still_refuses(board) -> None:
    was, board.KNOWN_COLLISIONS = board.KNOWN_COLLISIONS, set()
    try:
        problems = board.check(_COLLIDING)
        assert any("one number, two items" in line for line in problems), problems
        assert board.accepted_collisions(_COLLIDING) == []
    finally:
        board.KNOWN_COLLISIONS = was


def test_a_decided_repeat_is_named_and_does_not_refuse(board) -> None:
    # C-1957's owner settled it in their completion line - a claim's headline
    # is the item's identity and is not rewritten once pushed, and one side is
    # now a finished record. Recording that is not the same as hiding it.
    was, board.KNOWN_COLLISIONS = board.KNOWN_COLLISIONS, {"C-8002"}
    try:
        left = board.check(_COLLIDING)
        assert not any("C-8002" in line for line in left), left
        assert any("C-8003" in line for line in left), left
        named = board.accepted_collisions(_COLLIDING)
        assert len(named) == 1 and "C-8002" in named[0], named
    finally:
        board.KNOWN_COLLISIONS = was


def test_the_real_boards_settled_repeats_are_printed(board) -> None:
    # The listing that was only ever in source. Both of today's are decided,
    # so both must be visible and neither may refuse.
    live = (_ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    named = board.accepted_collisions(live)
    assert {"C-1011", "C-1957"} <= {
        number for number in ("C-1011", "C-1957")
        if any(number in line for line in named)
    }, named
    assert not board.check(live), board.check(live)
