"""C-1281: the saved report discloses that evidence was set aside as off-topic.

The document generator drops facts that share no subject term with the request
(C-1403). The chat summary said so, but the summary is shown once and the .md
file is the artifact that is saved and forwarded - it disclosed nothing, so a
report that had quietly left out evidence read as the complete sourced picture.
The file now discloses the withholding in 「まだ埋まっていないこと」, without a
count (a digit naming nothing in the evidence is what the validator catches).
"""

from __future__ import annotations

import tempfile

from sidra_ai.creation.document_job import build_document_generator
from sidra_ai.creation.documents import generate_document, validate_document
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.document_discloses_set_aside_evidence import (
    evaluate_document_discloses_set_aside_evidence,
)

_DISCLOSURE = "載せていません"
_REQUEST = "新機能ローンチの週次進捗レポートを作って"


def _saved(request: str, facts):
    from pathlib import Path

    generate = build_document_generator(tempfile.mkdtemp(prefix="doc-aside-t-"))
    out = generate(request, detect_creation_intent(request), list(facts))
    return Path(out.artifact_path).read_text(encoding="utf-8"), out


def test_document_discloses_set_aside_evidence_eval_passes():
    result = evaluate_document_discloses_set_aside_evidence()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_saved_file_discloses_when_a_fact_was_set_aside():
    facts = [
        Fact("新機能ローンチの登録数は初週で 1,240 件に達した。", "r:docs/launch.md"),
        Fact("未対応の不具合は 3 件が残っており、来週の対応を予定。", "r:docs/bugs.md"),
    ]
    md, out = _saved(_REQUEST, facts)
    assert out.details["off_topic_facts"] == 1
    assert _DISCLOSURE in md
    section = md.split("## まだ埋まっていないこと", 1)[1].split("## 出典", 1)[0]
    assert _DISCLOSURE in section
    # the summary still discloses too
    assert _DISCLOSURE in out.summary


def test_saved_file_stays_silent_when_nothing_set_aside():
    facts = [
        Fact("新機能ローンチの登録数は初週で 1,240 件に達した。", "r:docs/launch.md"),
        Fact("新機能ローンチの週次進捗は順調に推移している。", "r:docs/status.md"),
    ]
    md, out = _saved(_REQUEST, facts)
    assert out.details["off_topic_facts"] == 0
    assert _DISCLOSURE not in md


def test_disclosure_introduces_no_fabricated_number():
    fact = Fact("新機能ローンチの登録数は初週で 1,240 件に達した。", "r:docs/launch.md")
    doc = generate_document(_REQUEST, facts=[fact], set_aside=1)
    assert _DISCLOSURE in doc.markdown
    assert validate_document(doc, [fact])["usable"]


def test_set_aside_zero_leaves_document_unchanged():
    fact = Fact("新機能ローンチの登録数は初週で 1,240 件に達した。", "r:docs/launch.md")
    doc = generate_document(_REQUEST, facts=[fact], set_aside=0)
    assert _DISCLOSURE not in doc.markdown
