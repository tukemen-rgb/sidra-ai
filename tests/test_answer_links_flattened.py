"""C-1227: a cited Markdown link must read as text, not bracketed URL syntax.

A generated document carried 「[SPEC.md](../[REDACTED:high_entropy:…].md)」 -
link brackets, a URL, and an alarming redaction placeholder in what was a
relative path. ``plain_text`` now keeps the link text and drops the URL,
including a window-cut link, while a bare 「[1]」/「[S1]」 reference is left
alone.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.answer_links_flattened import evaluate_answer_links_flattened


def test_answer_links_flattened_eval_passes():
    result = evaluate_answer_links_flattened()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_plain_text_flattens_links_and_drops_redacted_url():
    assert plain_text("[SPEC.md](../SPEC.md) を参照。") == "SPEC.md を参照。"
    out = plain_text("[SPEC.md](../[REDACTED:high_entropy:31d60b69].md) — 現状")
    assert "REDACTED" not in out and "](" not in out and "SPEC.md" in out
    assert plain_text("参照: [docs/x.md](..") == "参照: docs/x.md"


def test_plain_text_keeps_bare_bracket_references():
    assert plain_text("根拠は [1] にある") == "根拠は [1] にある"
    assert plain_text("出典 [S1] を参照") == "出典 [S1] を参照"
    assert plain_text("状態 [記録] のまま") == "状態 [記録] のまま"
