"""C-1883: the web page strips terminal-control/bidi chars from DATA it renders.

The CLI removes these on output (C-1627); the page did not, and the ingestion
gate lets bidi isolates (U+2066-2069), C1 and ESC through to the excerpt. These
tests pin that each DATA insertion goes through clean() and that clean() covers
the dangerous ranges.
"""

from __future__ import annotations

import re

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_strips_terminal_controls_from_evidence import (
    evaluate_ui_strips_terminal_controls_from_evidence,
)


def test_eval_passes():
    result = evaluate_ui_strips_terminal_controls_from_evidence()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_answer_and_excerpt_go_through_clean():
    assert re.search(r"answer\.textContent\s*=\s*clean\(", ASK_PAGE)
    assert re.search(r"evidence\.textContent\s*=\s*clean\(", ASK_PAGE)


def test_clean_covers_the_reachable_ranges():
    fn = ASK_PAGE[ASK_PAGE.find("function clean("):]
    fn = fn[:900].lower()
    # the three families the gate lets through and the CLI strips
    assert "0x2066" in fn and "0x2069" in fn  # bidi isolates
    assert "0x9f" in fn                        # C1
    assert "0x202e" in fn                      # RLO (defence in depth)
