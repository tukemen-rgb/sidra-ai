"""Reloading the index from its persisted log.

Without a reload the index dies with the process and every repository has to
be re-ingested from GitHub, which is the expensive half of the work. The
subtlety is that the log records past decisions, not standing permissions.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.search import BM25Retriever
from sidra_ai.retrieval.store import DocumentStore, PersistenceError
from sidra_ai.security.gate import GatePolicy, SecurityGate

REPO = "tukemen-rgb/site"
FAKE_TOKEN = "ghp_" + "6" * 36


def _document(path: str, content: str) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=REPO,
            path=path,
            commit_sha="a" * 40,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


@pytest.fixture
def gate() -> SecurityGate:
    return SecurityGate(GatePolicy(), allowed_repositories=(REPO,))


@pytest.fixture
def path(tmp_path):
    return tmp_path / "index.jsonl"


# --- round trip --------------------------------------------------------

def test_index_survives_a_restart(gate, path) -> None:
    writer = DocumentStore(gate, path=path)
    writer.add(_document("a.md", "SIDRA local first retrieval design"))
    writer.add(_document("b.md", "GitHub read only ingestion with commit sha diff"))

    reader = DocumentStore(gate, path=path)
    assert len(reader) == 0, "a fresh store must start empty"
    report = reader.load()

    assert report.loaded == 2
    assert report.ok
    assert len(reader) == 2
    assert reader.chunk_count == writer.chunk_count


def test_reloaded_documents_are_searchable(gate, path) -> None:
    writer = DocumentStore(gate, path=path)
    writer.add(_document("b.md", "GitHub read only ingestion with commit sha diff"))

    reader = DocumentStore(gate, path=path)
    reader.load()
    results = BM25Retriever(reader).search("commit sha ingestion", top_k=2)
    assert [r.provenance.path for r in results] == ["b.md"]


def test_provenance_survives_the_round_trip(gate, path) -> None:
    """A citation that loses its commit after a restart is not a citation."""

    writer = DocumentStore(gate, path=path)
    writer.add(_document("a.md", "retrieval augmented generation over github"))

    reader = DocumentStore(gate, path=path)
    reader.load()
    provenance = reader.documents()[0].provenance
    assert provenance.repository == REPO
    assert provenance.commit_sha == "a" * 40
    assert provenance.license == "MIT"
    assert provenance.source_type is SourceType.DOCS


def test_loading_an_absent_log_is_not_an_error(gate, tmp_path) -> None:
    store = DocumentStore(gate, path=tmp_path / "never-written.jsonl")
    report = store.load()
    assert report.records == 0
    assert report.ok


def test_a_store_without_persistence_refuses_to_load(gate) -> None:
    with pytest.raises(PersistenceError):
        DocumentStore(gate).load()


# --- the log is a cache of decisions, not standing permission ----------

def test_reload_rescreens_under_current_policy(gate, path) -> None:
    """A tightened detector must not be undone by a restart.

    A record written when it was ALLOW can be QUARANTINE today. Loading it
    blindly would resurrect content the current policy rejects and silently
    undo the fix.
    """

    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    smuggled = _document("leak.md", f"deploy key {FAKE_TOKEN}")
    path.write_text(json.dumps(smuggled.to_dict(), ensure_ascii=False) + "\n",
                    encoding="utf-8")

    store = DocumentStore(gate, path=path)
    report = store.load()

    assert report.loaded == 0
    assert report.rejected == 1
    assert not report.ok
    assert len(store) == 0
    for chunk in store.chunks():
        assert FAKE_TOKEN not in chunk.content


def test_rejections_are_reported_not_swallowed(gate, path) -> None:
    """A reload that dropped half the corpus must not look healthy."""

    import json

    records = [
        _document("ok.md", "ordinary documentation about retrieval").to_dict(),
        _document("bad.md", f"token {FAKE_TOKEN}").to_dict(),
    ]
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )

    report = DocumentStore(gate, path=path).load()
    assert report.records == 2
    assert report.loaded == 1
    assert report.rejected == 1
    assert report.rejected_reasons
    assert FAKE_TOKEN not in " ".join(report.rejected_reasons)


def test_rescreen_can_be_disabled_explicitly(gate, path) -> None:
    """The unsafe path exists but must be asked for by name."""

    writer = DocumentStore(gate, path=path)
    writer.add(_document("a.md", "ordinary documentation"))
    reader = DocumentStore(gate, path=path)
    assert reader.load(rescreen=False).loaded == 1


# --- damaged logs ------------------------------------------------------

def test_a_torn_final_line_does_not_lose_earlier_records(gate, path) -> None:
    """A crash mid-append must cost one record, not the whole index."""

    writer = DocumentStore(gate, path=path)
    writer.add(_document("a.md", "first document about retrieval"))
    writer.add(_document("b.md", "second document about ingestion"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"content": "truncated mid')

    report = DocumentStore(gate, path=path).load()
    assert report.loaded == 2
    assert report.unreadable == 1


def test_a_record_missing_provenance_is_skipped_not_guessed(gate, path) -> None:
    """Inventing a commit to make a record loadable would poison citations."""

    import json

    path.write_text(
        json.dumps({"content": "text with no provenance at all"}) + "\n",
        encoding="utf-8",
    )
    report = DocumentStore(gate, path=path).load()
    assert report.loaded == 0
    assert report.unreadable == 1


def test_nothing_is_installed_until_the_whole_file_is_read(gate, path) -> None:
    """A half-loaded index is worse than an empty one."""

    writer = DocumentStore(gate, path=path)
    writer.add(_document("a.md", "first document"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"content": "torn')

    reader = DocumentStore(gate, path=path)
    reader.load()
    assert len(reader) == 1


def test_the_newest_revision_of_a_path_wins(gate, path) -> None:
    """Two revisions of one file must not both stay retrievable."""

    writer = DocumentStore(gate, path=path)
    writer.add(_document("a.md", "the first version of this document"))
    writer.add(_document("a.md", "the second version of this document"))

    reader = DocumentStore(gate, path=path)
    reader.load()
    assert len(reader) == 1
    assert "second version" in reader.documents()[0].content


# --- rescreening the running index -------------------------------------
# load() covers a restart. It does not cover the process that is already
# running: tighten a detector and the documents in memory keep serving the
# old verdict until someone restarts.

def test_rescreen_evicts_what_no_longer_passes(gate, tmp_path) -> None:
    from sidra_ai.security.detectors import PIIDetector, SecretDetector

    store = DocumentStore(gate)
    store.add(_document("safe.md", "ordinary documentation about retrieval"))
    store.add(_document("borderline.md", "the codeword is antidisestablishment"))
    assert len(store) == 2

    class Stricter(SecretDetector):
        def detect(self, content: str):
            from sidra_ai.security.detectors import DetectionOutput
            from sidra_ai.security.decisions import (
                Finding, FindingCategory, Severity,
            )
            if "codeword" not in content:
                return super().detect(content)
            return DetectionOutput((
                Finding(
                    category=FindingCategory.SECRET,
                    severity=Severity.CRITICAL,
                    detector="codeword",
                    reason="a newly recognised credential shape",
                ),
            ))

    gate._secret = Stricter()
    report = store.rescreen_all()

    assert report.records == 2
    assert report.loaded == 1
    assert report.rejected == 1
    assert len(store) == 1
    assert store.documents()[0].provenance.path == "safe.md"


def test_rescreen_is_a_no_op_when_policy_is_unchanged(gate) -> None:
    store = DocumentStore(gate)
    store.add(_document("a.md", "ordinary documentation about retrieval"))
    store.add(_document("b.md", "ingestion notes with a commit reference"))

    report = store.rescreen_all()
    assert report.loaded == 2
    assert report.rejected == 0
    assert report.ok
    assert len(store) == 2


def test_evicted_documents_are_quarantined_not_lost(tmp_path) -> None:
    """A demotion with a record, not a deletion."""

    from sidra_ai.security.gate import QuarantineStore
    from sidra_ai.security.quarantine_review import QuarantineReview

    quarantine = QuarantineStore(tmp_path / "q.jsonl")
    lenient = SecurityGate(
        GatePolicy(), allowed_repositories=(REPO,), quarantine_store=quarantine
    )
    store = DocumentStore(lenient)
    store.add(_document("a.md", "ordinary documentation"))

    class RejectEverything:
        def detect(self, content: str):
            from sidra_ai.security.detectors import DetectionOutput
            from sidra_ai.security.decisions import (
                Finding, FindingCategory, Severity,
            )
            return DetectionOutput((
                Finding(
                    category=FindingCategory.SECRET,
                    severity=Severity.CRITICAL,
                    detector="policy_change",
                    reason="newly forbidden",
                ),
            ))

    lenient._secret = RejectEverything()
    store.rescreen_all()

    assert len(store) == 0
    entries = QuarantineReview(quarantine.path).entries()
    assert entries, "the evicted document left no record"
    assert entries[-1].document_id


def test_rescreen_leaves_the_persisted_log_untouched(gate, path) -> None:
    """The log is history: rewriting it would destroy the evidence."""

    store = DocumentStore(gate, path=path)
    store.add(_document("a.md", "ordinary documentation about retrieval"))
    before = path.read_bytes()
    store.rescreen_all()
    assert path.read_bytes() == before


def test_a_detector_that_raises_leaves_the_index_intact(gate) -> None:
    """Half an index is worse than an unchanged one."""

    store = DocumentStore(gate)
    store.add(_document("a.md", "first document about retrieval"))
    store.add(_document("b.md", "second document about ingestion"))

    class Exploding:
        def detect(self, content: str):
            raise RuntimeError("detector bug")

    gate._secret = Exploding()
    with pytest.raises(PersistenceError, match="unchanged"):
        store.rescreen_all()
    assert len(store) == 2
