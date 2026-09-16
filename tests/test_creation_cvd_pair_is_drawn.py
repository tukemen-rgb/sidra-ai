"""The colour pair the CVD judge separates is the pair the page paints (C-1891).

``creation_cvd_info_pair`` reads ``theme.tokens`` and never opens a page. Its
arithmetic is right; its premise was untested. These tests pin the premise and
the shape of the exception list.
"""

from __future__ import annotations

from sidra_ai.creation.games import TEMPLATES
from sidra_ai.evals.cvd_pair_is_drawn import (
    CVD_PAIR_UNDRAWN,
    FRAMES,
    evaluate_cvd_pair_is_drawn,
)


def test_every_template_is_painted_or_explained() -> None:
    result = evaluate_cvd_pair_is_drawn()
    assert result.failures == ()
    assert result.passed
    assert result.accounted == len(TEMPLATES) == 10
    assert len(result.painting) == 8
    assert set(CVD_PAIR_UNDRAWN) == {"marble", "platformer"}


def test_the_exceptions_say_why_in_words() -> None:
    for key, why in CVD_PAIR_UNDRAWN.items():
        assert key in TEMPLATES, key
        assert len(why.strip()) > 20, key


def test_the_window_is_long_enough_to_see_a_spawn() -> None:
    """Three frames reported racing as painting no alert.

    Its obstacles are MAGENTA_TOKEN squares that spawn on an interval, so the
    short window missed them entirely - a sample too short is indistinguishable
    from a feature that is not there. The number is a real parameter and this
    keeps it from drifting back down.
    """

    assert FRAMES >= 600


def test_the_judge_reads_the_page_not_the_palette() -> None:
    """The whole point: this one opens a page, unlike the judge it backs up."""

    from sidra_ai.evals import cvd_pair_is_drawn as mod

    source = open(mod.__file__, encoding="utf-8").read()
    assert "generate_game(" in source
    assert "fillStyle" in source


def test_a_reason_is_not_a_way_to_excuse_everything() -> None:
    """Both directions, stated as a property of the judge.

    A template listed in CVD_PAIR_UNDRAWN has to really be missing what its
    reason says is missing; otherwise writing a reason for all ten would score
    full marks.
    """

    result = evaluate_cvd_pair_is_drawn()
    assert set(result.painting) & set(CVD_PAIR_UNDRAWN) == set()
