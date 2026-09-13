"""C-1775: the adapt panel announces a step only when a step was taken.

``adaptEasing()`` (what the panel says) used streak/manual/rung-count but not
the floor, while ``adaptSpeed()`` (what actually eases) bails at the easiest
rung. So an easy-difficulty game on a losing streak printed 「1 段やさしく」 when
nothing had changed. ``adaptEasing()`` is now floor-aware and agrees with
``adaptSpeed``.
"""

from __future__ import annotations

import shutil

import pytest

from sidra_ai.evals.adapt_panel_easing_matches_actual_ease import (
    _probe,
    evaluate_adapt_panel_easing_matches_actual_ease,
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to run the adapt preamble"
)

_EASE = "やさしく"


def test_adapt_panel_eval_passes():
    result = evaluate_adapt_panel_easing_matches_actual_ease()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_no_step_is_announced_at_the_floor():
    floor = _probe(1.0, 3)  # easiest rung, three losses
    assert floor["speedOut"] == floor["base"]  # adaptSpeed really did nothing
    assert _EASE not in (floor["panel"] or "")  # ...and the panel does not claim it
    assert floor["panel"] == "今の調整: 標準"


def test_a_step_above_the_floor_is_announced():
    mid = _probe(2.0, 3)
    assert mid["eased"] and mid["speedOut"] < mid["base"]
    assert _EASE in (mid["panel"] or "")


def test_below_the_threshold_is_silent():
    below = _probe(2.0, 2)
    assert _EASE not in (below["panel"] or "")
