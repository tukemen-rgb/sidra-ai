"""The end screen's headline is centred by the font, not by counting (C-1896)."""

from __future__ import annotations

import pytest

from sidra_ai.creation.browser import chromium_path
from sidra_ai.creation.games import TEMPLATES
from sidra_ai.evals.end_text_is_centred import (
    END_STATES,
    NO_END_SCREEN,
    TOLERANCE_PX,
    evaluate_end_text_is_centred,
)

needs_browser = pytest.mark.skipif(
    chromium_path() is None, reason="no Chromium on this machine"
)


@pytest.fixture(scope="module")
def result():
    return evaluate_end_text_is_centred()


@needs_browser
def test_every_end_screen_is_centred(result):
    assert result.passed, "; ".join(result.failures)


@needs_browser
def test_every_page_was_actually_opened(result):
    assert len(result.centred) == len(END_STATES)
    assert result.checks_total == result.checks_passed


def test_every_template_is_measured_or_explained():
    # A page left out of both tables would never be looked at, and the
    # number would not notice.
    assert set(END_STATES) | set(NO_END_SCREEN) == set(TEMPLATES)
    assert not set(END_STATES) & set(NO_END_SCREEN)


def test_the_tolerance_would_have_caught_the_defect():
    # C-1896 measured 51.7px of drift on shooter's result line.
    assert TOLERANCE_PX < 5.0


def test_a_missing_browser_is_not_a_pass():
    # A judge that cannot run says so; it does not report the pages correct.
    from sidra_ai.evals import end_text_is_centred as mod

    real = mod.chromium_path
    try:
        mod.chromium_path = lambda: None
        out = mod.evaluate_end_text_is_centred()
    finally:
        mod.chromium_path = real
    assert not out.passed
    assert out.ran is False
