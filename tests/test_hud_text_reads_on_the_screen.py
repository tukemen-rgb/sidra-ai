"""The HUD's ink, where it landed (C-1986, §4 / WCAG 1.4.3).

The judge reads the composited frame. These tests hold the floor, and the
reason the reading is a median rather than a worst case.
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.evals.hud_text_reads_on_the_screen import (
    ASKS,
    FLOOR,
    _REPORT,
    evaluate_hud_text_reads_on_the_screen,
    read_template,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME


def test_the_floor_is_the_one_wcag_names() -> None:
    assert FLOOR == 4.5
    assert len(ASKS) == 4


def test_the_backdrop_is_sampled_beside_the_letters() -> None:
    """Row spans reached past the plate; the fix keeps within six pixels."""
    assert "x0 - 6" in _REPORT and "x0 + 6" in _REPORT


def test_no_worst_pixel_statistic() -> None:
    """A letter's own edge is anti-aliased into the plate.

    Measured: a 90th percentile of the neighbourhood read 1.5:1 on three of
    four templates - the glyph's edge, not a thin plate.
    """
    assert "worstRatio" not in _REPORT


def test_every_template_reads_where_the_ink_landed() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_hud_text_reads_on_the_screen()
    assert result.templates_that_read == result.templates_total, result.failures


def test_the_ink_is_really_on_the_screen() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    seen = read_template("catch")
    assert "err" not in seen, seen.get("err")
    assert seen["inkPixels"] > 50, seen
    assert seen["backSamples"] > seen["inkPixels"], seen
