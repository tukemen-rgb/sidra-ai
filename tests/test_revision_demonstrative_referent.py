"""C-1257: demonstratives (その/これ/それ/この) count as back-references.

After making a game, 「その配色を紙にして」 fell to the Q&A "no evidence" wall
because ``_BACK_REFERENCES`` had no demonstratives. Now such a message is a
revision with the right adjustment, while the make-verb and question-marker
vetoes still keep a creation request and a question off the reviser.
"""

from __future__ import annotations

from sidra_ai.creation.revise import detect_revision_intent
from sidra_ai.evals.revision_demonstrative_referent import (
    evaluate_revision_demonstrative_referent,
)


def test_revision_demonstrative_referent_eval_passes():
    result = evaluate_revision_demonstrative_referent()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_demonstratives_are_back_references():
    assert detect_revision_intent("その配色を紙にして").adjustments == {"theme": "paper"}
    assert detect_revision_intent("これをもっと速くして").adjustments == {"difficulty": "+1"}
    assert detect_revision_intent("それを難しくして").adjustments == {"difficulty": "+1"}
    assert detect_revision_intent("これのタイトルを「爆走」にして").adjustments == {"title": "爆走"}
    for message in ("その配色を紙にして", "これをもっと速くして", "それを難しくして"):
        assert detect_revision_intent(message).is_revision is True


def test_vetoes_still_hold_with_demonstratives():
    # A question that names a demonstrative stays a question.
    assert detect_revision_intent("それは何ですか").is_revision is False
    assert detect_revision_intent("これは難しいですか").is_revision is False
    # A creation request stays a creation, never a revision.
    assert detect_revision_intent("難しいゲームを作って").is_revision is False
    assert detect_revision_intent("これを作って").is_revision is False
    # A demonstrative with a change verb but no recognisable adjustment is
    # still not a revision (nothing to change) - unchanged by this fix.
    assert detect_revision_intent("それを直して").is_revision is False


def test_explicit_referents_unchanged():
    # The referents that already worked keep working (C-1126 lineage).
    assert detect_revision_intent("さっきのレースを難しくして").is_revision is True
    assert detect_revision_intent("前のゲームを簡単にして").is_revision is True
