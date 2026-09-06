"""C-1286: the ask page announces its async updates to assistive technology.

After a submit the page rewrites #status (loading/errors/refusals) and #answer
(the reply) with textContent. Neither was a live region, so a screen-reader user
heard nothing when the reply arrived (WCAG 4.1.3 Status Messages). #status now
carries role="status" and #answer aria-live="polite".
"""

from __future__ import annotations

import re

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ask_page_announces_async_updates import (
    evaluate_ask_page_announces_async_updates,
)


def _open_tag(element_id: str) -> str:
    m = re.search(rf'<[^>]*\bid="{element_id}"[^>]*>', ASK_PAGE)
    return m.group(0) if m else ""


def test_ask_page_announces_async_updates_eval_passes():
    result = evaluate_ask_page_announces_async_updates()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_status_region_is_live():
    tag = _open_tag("status")
    assert 'role="status"' in tag or 'aria-live="polite"' in tag


def test_answer_region_is_live():
    assert 'aria-live="polite"' in _open_tag("answer")


def test_live_regions_are_the_ones_the_js_updates():
    assert 'getElementById("status")' in ASK_PAGE and "statusLine.textContent" in ASK_PAGE
    assert 'getElementById("answer")' in ASK_PAGE and "answer.textContent" in ASK_PAGE
