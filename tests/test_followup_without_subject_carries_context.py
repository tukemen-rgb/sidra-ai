"""C-1453: a subject-less follow-up grounds on the topic under discussion.

The history-carry retry used to fire only when the bare follow-up retrieved
nothing. A Japanese elaboration phrase like 「もっと詳しく」 names no subject of its
own, so BM25 filled top_k on a glue bigram and cited an unrelated doc as the
elaboration. The carry now also fires when the follow-up has no subject term.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.evals.followup_without_subject_carries_context import (
    evaluate_followup_without_subject_carries_context,
)
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

_ALLOWED = ("tukemen-rgb/site",)


def _doc(content: str, path: str) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository="tukemen-rgb/site",
            path=path,
            commit_sha="c" * 40,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


@pytest.fixture
def svc(tmp_path) -> SidraService:
    settings = Settings(allowed_repositories=_ALLOWED, data_dir=str(tmp_path / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=_ALLOWED,
        quarantine_store=QuarantineStore(tmp_path / "q.jsonl"),
    )
    store = DocumentStore(gate)
    store.add(_doc("デプロイは必ず運用者の承認を得てから実行する。承認者は当番のリードエンジニアが務める。", "docs/deploy.md"))
    store.add(_doc("オンボーディング資料の詳しい手順は入社時に配布する。", "docs/onboarding.md"))
    store.add(_doc("マーケティングの週次レポートは毎週金曜に更新する。閲覧は社内限定。", "docs/marketing.md"))
    return SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)


def _paths(result):
    return [c["path"] for c in result["citations"]]


def test_followup_subject_eval_passes():
    result = evaluate_followup_without_subject_carries_context()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_elaboration_grounds_on_topic_not_glue_match(svc: SidraService):
    q1 = "デプロイの承認は誰がしますか"
    r1 = svc.chat(q1)
    assert _paths(r1)[:1] == ["docs/deploy.md"]

    follow = svc.chat("もっと詳しく", history=[(q1, r1["answer"])])
    assert _paths(follow)[:1] == ["docs/deploy.md"]


def test_new_subject_followup_is_not_carried_away(svc: SidraService):
    q1 = "デプロイの承認は誰がしますか"
    r1 = svc.chat(q1)
    mk = svc.chat("マーケティングのレポートは？", history=[(q1, r1["answer"])])
    assert _paths(mk)[:1] == ["docs/marketing.md"]


def test_single_turn_subject_query_unchanged(svc: SidraService):
    assert _paths(svc.chat("デプロイの承認"))[:1] == ["docs/deploy.md"]
