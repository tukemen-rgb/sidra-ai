"""The page's silence, read from the browser's own log (C-1983, §9).

The judge subtracts a control run. These tests hold the two things that
make that subtraction honest: the control is a page that only paints, and
``data:`` is not counted as traffic (the favicon is one, by design).
"""

from __future__ import annotations

import pathlib

import pytest

from sidra_ai.evals.canvas_matches_the_language_asked import TEMPLATE_ASKS
from sidra_ai.evals.nothing_leaves_the_page import (
    CONTROL,
    _place,
    _urls,
    evaluate_nothing_leaves_the_page,
)
from sidra_ai.evals.targets_meet_the_size_floor import CHROME


def test_the_control_asks_for_nothing_of_its_own() -> None:
    assert "src=" not in CONTROL and "href=" not in CONTROL
    assert "://" not in CONTROL


def test_a_data_uri_is_not_traffic() -> None:
    assert _place("data:image/png;base64,AAAA") is None
    assert _place("blob:null/1234") is None
    assert _place("https://example.test/a?b=1#c") == "https://example.test/a"


def test_the_browser_itself_is_the_floor_not_zero() -> None:
    """Measured: a blank page still draws four requests in this build."""
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    floor = _urls(CONTROL, drive=False)
    assert floor, "the control asked for nothing at all - the log was not read"


def test_every_template_adds_nothing() -> None:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    result = evaluate_nothing_leaves_the_page()
    assert result.templates_that_say_nothing == len(TEMPLATE_ASKS), result.failures
