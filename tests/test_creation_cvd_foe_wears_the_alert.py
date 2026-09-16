"""The foe is the one wearing the alert colour (C-1903, §4 事実 1)."""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import TEMPLATES
from sidra_ai.evals.cvd_foe_wears_the_alert import (
    FOE_PAGES,
    NO_FOE,
    NOT_YET_REACHED,
    evaluate_cvd_foe_wears_the_alert,
)


@pytest.fixture(scope="module")
def result():
    return evaluate_cvd_foe_wears_the_alert()


def test_the_foe_wears_the_alert_and_the_hero_does_not(result):
    assert result.passed, "; ".join(result.failures)


def test_every_measured_page_was_actually_stood_in_front_of(result):
    assert len(result.readings) == len(FOE_PAGES)
    assert result.checks_total == result.checks_passed


def test_every_template_sits_in_exactly_one_table():
    tables = (set(FOE_PAGES), set(NO_FOE), set(NOT_YET_REACHED))
    assert tables[0] | tables[1] | tables[2] == set(TEMPLATES)
    assert sum(len(t) for t in tables) == len(set(TEMPLATES))


def test_a_page_with_a_foe_is_not_excused_as_having_none():
    # adventure draws its roamers with MAGENTA_TOKEN, so calling it
    # foe-less would be a false excuse; it is named as unreached instead.
    assert "adventure" in NOT_YET_REACHED
    assert "adventure" not in NO_FOE
    assert NOT_YET_REACHED["adventure"].strip()
