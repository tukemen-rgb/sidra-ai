"""The canvas tells a reader who cannot see it what is there (C-1907, §36)."""

from __future__ import annotations

import pytest

from sidra_ai.evals.canvas_names_itself import (
    MIN_BEYOND_TITLE,
    MIN_CHARS,
    canvas_alternative,
    evaluate_canvas_names_itself,
)


@pytest.fixture(scope="module")
def result():
    return evaluate_canvas_names_itself()


def test_every_canvas_identifies_its_page(result):
    assert result.passed, "; ".join(result.failures)


def test_every_kind_was_read(result):
    assert len(result.readings) == 3
    assert result.checks_total == result.checks_passed


def test_an_empty_canvas_is_not_an_alternative():
    # The state all three pages shipped in, and the one the old validators
    # ("<canvas" in html) accepted.
    assert canvas_alternative('<canvas id="a" width="1" height="1"></canvas>') == ""


def test_markup_inside_the_canvas_still_reads_as_text():
    # Fallback content may be a sub-DOM rather than a bare string.
    alt = canvas_alternative('<canvas><p>ある絵の説明</p></canvas>')
    assert alt == "ある絵の説明"


def test_the_thresholds_are_the_kind_that_would_have_caught_it():
    assert MIN_CHARS > 0 and MIN_BEYOND_TITLE > 0
