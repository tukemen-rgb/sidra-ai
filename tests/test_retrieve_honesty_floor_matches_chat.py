"""C-1477: /v1/retrieve abstains on all-glue matches, like /v1/chat.

chat() carries the C-1468/C-1453 honesty floor; retrieve() did not, so a query
about something the corpus does not cover came back with glue-matched documents
presented as its sources. retrieve() now applies the same floor, while a query
whose subject the corpus carries still returns its sources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate
from sidra_ai.evals.retrieve_honesty_floor_matches_chat import (
    evaluate_retrieve_honesty_floor_matches_chat,
)

_README = (
    "SIDRA STUDIO の広告サイトについて詳しく説明します。"
    "料金ページの構成について教えます。事例ページの使い方も詳しく案内します。"
    "お問い合わせについては下記をご覧ください。導入手順について順に説明します。"
)
_ARCH = (
    "本システムの構成について詳しく述べます。索引の仕組みについて教えます。"
    "検索の流れについて詳しく説明します。運用についてはこちらをご覧ください。"
    "設定項目について順に案内します。ログ収集について詳しく記します。"
)


@pytest.fixture
def service(tmp_path) -> SidraService:
    repo = "tukemen-rgb/site"
    settings = Settings(allowed_repositories=(repo,), data_dir=str(tmp_path / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repo,),
        quarantine_store=QuarantineStore(tmp_path / "q.jsonl"),
    )
    store = DocumentStore(gate)
    for path, body in (("README.md", _README), ("docs/arch.md", _ARCH)):
        prov = Provenance(
            source="github", repository=repo, path=path, commit_sha="a" * 40,
            timestamp=datetime(2026, 9, 7, tzinfo=timezone.utc),
            source_type=SourceType.DOCS, trust_level=TrustLevel.INTERNAL_REPO,
            license="proprietary",
        )
        store.add(Document(content=body, provenance=prov))
    return SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)


def test_retrieve_floor_eval_passes():
    result = evaluate_retrieve_honesty_floor_matches_chat()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 11


@pytest.mark.parametrize("query", [
    "宇宙旅行について詳しく教えてください",
    "退職手続きについて教えてください",
    "もっと詳しく教えてください",
])
def test_retrieve_abstains_on_off_corpus_glue(service, query):
    r = service.retrieve(query, top_k=5)
    assert r["results"] == []
    assert r["refused"] is False
    assert r["reason"] == "no indexed evidence matched the query"
    # parity: chat abstains on the same query
    assert service.chat(query, top_k=5)["citations"] == []


def test_retrieve_still_returns_in_corpus_sources(service):
    r = service.retrieve("料金ページについて教えて", top_k=5)
    assert r["results"]
    assert service.chat("料金ページについて教えて", top_k=5)["citations"]
