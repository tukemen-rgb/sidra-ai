"""C-1203: facts in generated documents must carry real provenance.

``_facts_for`` read ``repository``/``path`` off the chunk itself; ``Chunk``
keeps them under ``provenance``, so every fact's source label was "" and the
document generator rendered 「出典不明」 for excerpts it was quoting - while
the sources section claimed nothing had been retrieved at all.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel

REPOSITORY = "tukemen-rgb/site"


def _document(content: str, *, path: str) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=REPOSITORY,
            path=path,
            commit_sha="c" * 40,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


@pytest.fixture
def service(settings: Settings, store, gate) -> SidraService:
    return SidraService(settings, store=store, gate=gate)


def test_facts_carry_repository_and_path(service: SidraService):
    service.store.add(
        _document("広告の方針: 第三者 JS は載せない。", path="docs/ads.md")
    )

    facts = service._facts_for("広告の方針", top_k=3, repositories=None)

    assert facts, "the subject-matched chunk must come back as a fact"
    assert facts[0].source == f"{REPOSITORY} docs/ads.md"


def test_generated_document_names_its_sources(service: SidraService):
    service.store.add(
        _document("広告の方針: 第三者 JS は載せない。", path="docs/ads.md")
    )

    result = service.chat("広告の方針のレポートを作って")
    outcome = result["creation"]["outcome"]
    assert outcome["handled"] and outcome["kind"] == "document"

    markdown = Path(outcome["artifact_path"]).read_text(encoding="utf-8")
    assert "出典不明" not in markdown
    assert f"{REPOSITORY} docs/ads.md" in markdown


def test_document_provenance_eval_passes():
    from sidra_ai.evals.document_provenance import evaluate_document_provenance

    result = evaluate_document_provenance()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4
