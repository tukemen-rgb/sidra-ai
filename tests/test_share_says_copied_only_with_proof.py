"""The copy, and the claim about it (C-1988, §8 事実 7).

The judge drives one page to the end of a round. These tests hold the two
halves of the promise: the page tries both ways, and the button waits for
one of them to answer.
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.creation.share import SHARE_PREAMBLE
from sidra_ai.evals.share_says_copied_only_with_proof import (
    FRAMES,
    evaluate_share_says_copied_only_with_proof,
    read_page,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME


def test_the_button_speaks_from_one_place() -> None:
    """Both ways end at the same line, so neither can claim on its own."""
    assert SHARE_PREAMBLE.count("SHARE_BUTTON.textContent=CW.copied") == 1
    assert "function shareSaidCopied()" in SHARE_PREAMBLE


def test_the_old_trick_is_still_tried() -> None:
    """A promise that has not answered is not an answer."""
    assert "document.execCommand&&document.execCommand('copy')" in SHARE_PREAMBLE
    assert "p.then(shareSaidCopied" in SHARE_PREAMBLE


def test_the_round_must_end_before_a_result_can_be_shared() -> None:
    assert FRAMES >= 4000, "shareReady() is false until the round is over"


def test_the_page_does_not_claim_a_copy_it_cannot_prove() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_share_says_copied_only_with_proof()
    assert result.checks_passed == result.checks_total, result.failures


def test_the_line_it_copies_is_the_line_it_shows() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    seen = read_page()
    assert "err" not in seen, seen.get("err")
    assert seen["last"] and seen["last"] == seen["text"], seen
