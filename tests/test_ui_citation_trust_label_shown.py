"""C-1471: the web UI shows a citation's trust level, like the CLI (C-1469).

The browser page showed the redaction flags but never read c.trust_level, so an
Issue/PR body's EXTERNAL trust was invisible there. The page now surfaces it
with the same Japanese labels, internal_repo suppressed, markup never rendered.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_citation_trust_label_shown import (
    evaluate_ui_citation_trust_label_shown,
)


def test_ui_trust_label_eval_passes():
    result = evaluate_ui_citation_trust_label_shown()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_page_branches_on_trust_level():
    assert re.search(r"c\.trust_level", ASK_PAGE)
    assert "internal_repo" in ASK_PAGE


@pytest.mark.parametrize("label", ["外部", "未検証", "運用者", "システム"])
def test_page_carries_japanese_trust_labels(label):
    assert label in ASK_PAGE


def test_redaction_flags_unchanged():
    assert re.search(r"c\.redacted", ASK_PAGE)
    assert re.search(r"c\.excerpt_withheld", ASK_PAGE)
    assert "伏せ字あり" in ASK_PAGE
    assert "抜粋を秘匿" in ASK_PAGE
