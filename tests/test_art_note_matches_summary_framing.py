"""C-1801: the art default-pattern note is framed like the chat summary.

A bare 「アートを作って」 named no pattern; the page note used to say 「依頼「アート」
に合うパターン名が無かった」, quoting the medium as a failed pattern request. It now
uses the summary's subjectless framing 「依頼にパターン名が無かった」, still names the
flow default, and lists the selectable patterns. A named pattern gets no note.
"""

from __future__ import annotations

import re

from sidra_ai.creation.art import generate_art
from sidra_ai.evals.art_note_matches_summary_framing import (
    evaluate_art_note_matches_summary_framing,
)


def _notes(request: str) -> str:
    html = generate_art(request).html
    return " ".join(re.findall(r'<p class="note">(.*?)</p>', html, re.DOTALL))


def test_art_note_framing_eval_passes():
    result = evaluate_art_note_matches_summary_framing()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_bare_request_note_does_not_bracket_quote_the_medium():
    note = _notes("アートを作って")
    assert "依頼「" not in note
    assert "既定の「フロー」" in note
    assert "フロー" in note and "軌道" in note


def test_subject_request_note_does_not_bracket_quote_but_still_discloses():
    note = _notes("猫のアートを作って")
    assert "依頼「" not in note
    assert "既定の「フロー」" in note


def test_named_pattern_carries_no_note():
    assert '<p class="note">' not in generate_art("軌道のアートを作って").html
