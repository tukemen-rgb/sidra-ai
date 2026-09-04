"""C-1236: a withheld-excerpt citation is flagged, not shown like any other.

An ingestion-time redaction shows as 「一部秘匿」/「（伏せ字あり）」; when the
output guard blocks a whole excerpt at answer time the service sets
excerpt_withheld so the two can be told apart. The CLI and the web page now
surface a withheld mark beside the redacted one.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout

from sidra_ai.api.ask_cli import _Stripped, _print_citations
from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.citation_withheld_flagged import (
    evaluate_citation_withheld_flagged,
)


def _cli(citation: dict) -> str:
    out = io.StringIO()
    with redirect_stdout(out):
        _print_citations({"citations": [citation]}, _Stripped())
    return out.getvalue()


def test_citation_withheld_eval_passes():
    result = evaluate_citation_withheld_flagged()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_cli_marks_withheld_distinct_from_redacted():
    base = {"label": "S1", "citation": "repo@x:a.md"}
    assert "抜粋を秘匿" in _cli({**base, "excerpt_withheld": True})
    redacted = _cli({**base, "redacted": True})
    assert "一部秘匿" in redacted and "抜粋を秘匿" not in redacted
    plain = _cli(base)
    assert "一部秘匿" not in plain and "抜粋を秘匿" not in plain


def test_web_page_surfaces_withheld_and_keeps_redacted():
    assert "excerpt_withheld" in ASK_PAGE
    assert "抜粋を秘匿" in ASK_PAGE
    assert "redacted" in ASK_PAGE
