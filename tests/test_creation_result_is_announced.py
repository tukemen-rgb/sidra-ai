"""The result of a run reaches a screen reader (C-1908, WCAG 4.1.3)."""

from __future__ import annotations

import pytest

from sidra_ai.evals.end_text_is_centred import END_STATES
from sidra_ai.evals.result_is_announced import (
    FRAMES_AFTER_END,
    evaluate_result_is_announced,
)


@pytest.fixture(scope="module")
def result():
    return evaluate_result_is_announced()


def test_every_end_screen_says_its_result(result):
    assert result.passed, "; ".join(result.failures)


def test_every_page_with_an_end_screen_was_driven(result):
    assert len(result.readings) == len(END_STATES)
    assert result.checks_total == result.checks_passed


def test_the_window_is_long_enough_to_catch_a_repeat():
    # Saying it once a frame is the failure mode this guards; a one-frame
    # window could not tell that apart from saying it once.
    assert FRAMES_AFTER_END >= 30


def test_the_live_region_ships_in_the_page():
    from sidra_ai.creation.games import generate_game

    html = generate_game("シューティングゲームを作って").html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    # Off-screen, not removed: display:none would drop it from the
    # accessibility tree along with the layout.
    assert "display:none" not in html.split(".saidonly")[1].split("}}")[0]
