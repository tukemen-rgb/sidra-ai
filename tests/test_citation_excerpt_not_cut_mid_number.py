"""C-1849: a clipped citation excerpt does not end inside a number.

The citation-excerpt sibling of C-1217. The /v1/chat excerpt is capped and marks a
clipped tail with 「…」 (C-1264), but the cut landed mid-digit, so a figure
straddling the budget showed 「1,234,567,890 円」 as 「…1,2…」 - a partial number that
reads as a small whole value. The excerpt now drops a split figure back to its
start; a whole figure at the edge is kept, and the 「…」 still marks the clip.
"""

from __future__ import annotations

from sidra_ai.api.citations import citation_excerpt
from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS as _M
from sidra_ai.security.output_guard import OutputGuard
from sidra_ai.evals.citation_excerpt_not_cut_mid_number import (
    evaluate_citation_excerpt_not_cut_mid_number,
)

_GUARD = OutputGuard()
_HEAD = "売上について。"
_PAD = "あ" * (_M - len(_HEAD) - 4)


def _excerpt(content: str) -> str:
    return citation_excerpt(content, _GUARD, query="売上")[0]


def test_excerpt_number_eval_passes():
    result = evaluate_citation_excerpt_not_cut_mid_number()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_straddling_figure_is_not_shown_partially():
    excerpt = _excerpt(_HEAD + _PAD + "1,234,567,890 円で着地。")
    assert excerpt.endswith("…")          # still a slice
    assert "1,2" not in excerpt            # no partial number
    assert "売上" in excerpt               # real content kept


def test_whole_figure_at_the_edge_is_kept():
    content = _HEAD + "あ" * (_M - len(_HEAD) - 6) + "9,800円 ん" * 5
    assert "9,800" in _excerpt(content)


def test_uncut_excerpt_keeps_its_figure_and_has_no_mark():
    excerpt = _excerpt("売上は 1,234,567 円。")
    assert "…" not in excerpt
    assert "1,234,567" in excerpt
