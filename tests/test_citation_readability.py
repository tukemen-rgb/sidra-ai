"""C-1216: chat answers must quote evidence a reader can actually read.

The echo lead extractor split on sentence terminators, so a Markdown
heading label (「## D-CY4.」) and a checkbox stub (「**A.」) each counted
as a full sentence - the whole excerpt budget spent on raw decoration
before any content appeared. The lead now flattens the markup the way
generated documents already do (C-1212) and lets sub-sentence fragments
ride along without consuming a sentence slot.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.citation_readability import evaluate_citation_readability
from sidra_ai.models.echo import EchoModelAdapter


def test_citation_readability_eval_passes():
    result = evaluate_citation_readability()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_lead_reaches_content_past_label_fragments():
    lead = EchoModelAdapter()._lead(
        "## D-CY4. 決済を持つか（Recipe 販売・Mentor 料金・サブスク）\n"
        "- [ ] **A. 持たない**（無料のまま、収益はスポンサー枠で作る）\n"
    )
    assert "収益はスポンサー枠" in lead
    assert "##" not in lead and "**" not in lead and "- [ ]" not in lead
    # The label rides along - it is what a reader greps the source for.
    assert lead.startswith("D-CY4.")


def test_plain_prose_lead_is_unchanged():
    lead = EchoModelAdapter()._lead(
        "First sentence long enough to count. "
        "Second sentence also long enough to count. "
        "Third must not appear in the lead."
    )
    assert lead == (
        "First sentence long enough to count. "
        "Second sentence also long enough to count."
    )


def test_plain_text_strips_list_markers_only_at_line_start():
    assert plain_text("- [ ] やること\n- 済んだこと") == "やること 済んだこと"
    # A mid-sentence dash is content, not decoration.
    assert plain_text("速度は 3x - 5x の範囲。") == "速度は 3x - 5x の範囲。"
