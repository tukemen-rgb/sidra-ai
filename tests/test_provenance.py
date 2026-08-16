"""Provenance must never be lost between ingestion and citation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sidra_ai.documents import (
    Document,
    Provenance,
    ProvenanceError,
    SourceType,
    TrustLevel,
)
from sidra_ai.retrieval.chunker import chunk_document
from sidra_ai.security.data_envelope import build_data_context

REQUIRED = Provenance.REQUIRED_FIELDS


def _valid_kwargs() -> dict:
    return {
        "source": "github",
        "repository": "tukemen-rgb/site",
        "path": "README.md",
        "commit_sha": "a" * 40,
        "timestamp": datetime.now(timezone.utc),
        "source_type": SourceType.README,
        "trust_level": TrustLevel.INTERNAL_REPO,
        "license": "MIT",
    }


def test_required_fields_cover_the_v01_schema() -> None:
    assert set(REQUIRED) == {
        "source",
        "repository",
        "path",
        "commit_sha",
        "timestamp",
        "source_type",
        "trust_level",
        "license",
    }


@pytest.mark.parametrize("field", ["source", "repository", "path", "commit_sha", "license"])
def test_empty_required_string_is_rejected(field: str) -> None:
    kwargs = _valid_kwargs()
    kwargs[field] = "   "
    with pytest.raises(ProvenanceError):
        Provenance(**kwargs)


def test_naive_timestamp_is_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["timestamp"] = datetime(2026, 1, 1)
    with pytest.raises(ProvenanceError):
        Provenance(**kwargs)


def test_repository_must_be_owner_slash_name() -> None:
    kwargs = _valid_kwargs()
    kwargs["repository"] = "site"
    with pytest.raises(ProvenanceError):
        Provenance(**kwargs)


def test_unknown_license_is_recorded_not_dropped() -> None:
    """"We never checked" must be distinguishable from "no license"."""

    kwargs = _valid_kwargs()
    kwargs["license"] = "unknown"
    assert Provenance(**kwargs).license == "unknown"


def test_chunks_inherit_full_provenance() -> None:
    document = Document(
        content="# A\n\n" + ("body paragraph. " * 200) + "\n\n# B\n\nmore text",
        provenance=Provenance(**_valid_kwargs()),
    )
    chunks = chunk_document(document, max_chars=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.provenance == document.provenance
        for field in REQUIRED:
            assert getattr(chunk.provenance, field)
        assert chunk.document_id == document.doc_id


def test_citations_carry_every_provenance_field() -> None:
    document = Document(content="hello world", provenance=Provenance(**_valid_kwargs()))
    _, citations = build_data_context(chunk_document(document))
    assert len(citations) == 1
    citation = citations[0]
    for key in ("repository", "path", "commit_sha", "source_type", "trust_level", "license"):
        assert citation[key], f"citation lost provenance field {key!r}"
    assert citation["citation"] == "tukemen-rgb/site@aaaaaaa:README.md"


def test_ingested_documents_all_carry_provenance(
    client, store, gate, tmp_path, settings
) -> None:
    from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline
    from sidra_ai.ingestion.state import StateStore

    pipeline = GitHubIngestionPipeline(
        client=client,
        store=store,
        state_store=StateStore(tmp_path / "state.json"),
        gate=gate,
        settings=settings,
    )
    pipeline.ingest_repository("tukemen-rgb/site")

    assert len(store) > 0
    for document in store.documents():
        document.provenance.validate()
        assert document.provenance.source == "github"
        assert len(document.provenance.commit_sha) >= 7
    for chunk in store.chunks():
        chunk.provenance.validate()


def test_provenance_round_trips_through_serialization() -> None:
    original = Provenance(**_valid_kwargs())
    restored = Provenance.from_dict(original.to_dict())
    assert restored.to_dict() == original.to_dict()


def test_document_id_is_stable_and_content_sensitive() -> None:
    provenance = Provenance(**_valid_kwargs())
    a = Document(content="same", provenance=provenance)
    b = Document(content="same", provenance=provenance)
    c = Document(content="different", provenance=provenance)
    assert a.doc_id == b.doc_id
    assert a.doc_id != c.doc_id
