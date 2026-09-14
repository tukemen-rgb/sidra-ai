"""C-1831: a generated document/deck discloses an external/unverified source.

The chat citation flags 外部/未検証 (C-1471), but the forwardable artifacts named
only repo+path, so a third party's unverified Issue claim read as an internal
fact in the report an executive forwarded. The artifact now carries the same note
for a non-internal source, and an ordinary internal fact is unchanged.
"""

from __future__ import annotations

from sidra_ai.documents import SourceType, TrustLevel
from sidra_ai.evals.generated_artifact_discloses_source_trust import (
    _CLAIM,
    _artifact_text,
    evaluate_generated_artifact_discloses_source_trust,
)


def test_artifact_trust_eval_passes():
    result = evaluate_generated_artifact_discloses_source_trust()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_external_document_and_deck_disclose():
    doc = _artifact_text(TrustLevel.EXTERNAL, SourceType.ISSUE, "issues/42", "競合のレポートを作って")
    deck = _artifact_text(TrustLevel.EXTERNAL, SourceType.ISSUE, "issues/42", "競合のスライドを作って")
    assert _CLAIM[:8] in doc and "外部" in doc
    assert _CLAIM[:8] in deck and "外部" in deck


def test_internal_artifact_carries_no_note():
    doc = _artifact_text(TrustLevel.INTERNAL_REPO, SourceType.DOCS, "docs/x.md", "競合のレポートを作って")
    assert _CLAIM[:8] in doc
    assert "外部" not in doc and "未検証" not in doc
