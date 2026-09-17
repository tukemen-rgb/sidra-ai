"""C-1912: an English subject-less follow-up carries the topic under discussion.

"Tell me more" abstained ("No indexed evidence") because _own_content_subject
read tell/me/more as topic terms and the carry was skipped. An English
elaboration set (twin of _JP_ELABORATIONS) makes the pure-elaboration follow-up
ground on the previous subject; a follow-up that names a real subject keeps it.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import _own_content_subject
from sidra_ai.evals.chat_english_followup_carries_the_subject import (
    _ELABORATIONS,
    evaluate_chat_english_followup_carries_the_subject,
)


def test_eval_passes():
    result = evaluate_chat_english_followup_carries_the_subject()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 15


@pytest.mark.parametrize("phrase", _ELABORATIONS)
def test_elaboration_has_no_own_subject(phrase):
    # A pure elaboration names no topic of its own, so the carry fires.
    assert _own_content_subject(phrase) == ()


@pytest.mark.parametrize("phrase,expected", [
    ("tell me about billing", ("billing",)),
    ("How does deployment work?", ("deployment", "work")),
    ("what about the release notes", ("release", "notes")),
])
def test_real_subject_survives_elaboration_fillers(phrase, expected):
    # A real subject beside the fillers is kept, so the follow-up is not carried
    # off its own topic. (Order-independent membership check.)
    own = _own_content_subject(phrase)
    for term in expected:
        assert term in own, f"{term!r} dropped from {phrase!r}: {own}"
