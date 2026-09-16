"""A revision must not move what it was not asked about (C-1894, §9 事実 2)."""

from __future__ import annotations

import pytest

from sidra_ai.evals.revision_changes_only_what_it_owns import (
    AXIS_CASES,
    AXIS_OWNS,
    WIDE_OWNERSHIP,
    evaluate_revision_changes_only_what_it_owns,
)


@pytest.fixture(scope="module")
def result():
    return evaluate_revision_changes_only_what_it_owns()


def test_no_revision_strays_outside_what_it_owns(result):
    assert result.passed, "; ".join(result.failures)


def test_every_axis_was_actually_driven(result):
    assert len(result.clean) == len(AXIS_CASES)
    assert result.checks_total == result.checks_passed


def test_the_table_covers_the_axes_that_are_measured():
    # A sentence with no ownership row would be scored against an empty
    # set and could never pass; a row with no sentence is never driven.
    assert {axis for axis, _ in AXIS_CASES} == set(AXIS_OWNS)


def test_wide_ownership_is_explained_not_assumed():
    # Anything owning more than the field it is named after needs a
    # written reason - otherwise widening the table hides a leak.
    for axis, owns in AXIS_OWNS.items():
        its_own = "band" if axis == "band_up" else axis
        if owns - {its_own}:
            assert WIDE_OWNERSHIP.get(axis), axis
