from __future__ import annotations

from datetime import datetime, timezone

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel

REPO = "tukemen-rgb/site"
SHA = "a" * 40


def _document(
    *,
    source: str = "github",
    source_type: SourceType = SourceType.DOCS,
) -> Document:
    return Document(
        content="same retrievable content",
        provenance=Provenance(
            source=source,
            repository=REPO,
            path="shared.md",
            commit_sha=SHA,
            timestamp=datetime(2026, 8, 18, tzinfo=timezone.utc),
            source_type=source_type,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


def test_document_id_distinguishes_source_type_provenance(store) -> None:
    readme = _document(source_type=SourceType.README)
    docs = _document(source_type=SourceType.DOCS)

    assert readme.doc_id != docs.doc_id

    store.add(readme)
    store.add(docs)

    current = store.by_repository(REPO)
    assert len(current) == 2
    assert {document.provenance.source_type for document in current} == {
        SourceType.README,
        SourceType.DOCS,
    }
    assert len({chunk.document_id for chunk in store.chunks()}) == 2


def test_document_id_distinguishes_source_system_provenance() -> None:
    github = _document(source="github")
    mirror = _document(source="git_mirror")

    assert github.doc_id != mirror.doc_id
