"""The index file stops growing without bound - and shrinks atomically.

Append-only persistence left a dead record behind on every re-ingestion
(the C-1010 leftover): the index stayed correct because ``load()`` retires
superseded versions, while the file only ever grew. Compaction rewrites it
with the live documents, under two contracts these tests pin: the rewrite
is atomic (a temp file swapped in, never a torn target), and the file is a
cache of GitHub - dropping what the gate rejected is correct because
re-ingesting is always the way back.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.retrieval.store import DocumentStore


def _document(text: str, path: str = "docs/x.md") -> Document:
    return Document(
        content=text,
        provenance=Provenance(
            source="github",
            repository="tukemen-rgb/site",
            path=path,
            commit_sha="a" * 40,
            timestamp=datetime(2026, 8, 30, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


def _records(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def test_a_restart_compacts_the_dead_records_away(tmp_path: Path) -> None:
    service = SidraService(settings=Settings(data_dir=str(tmp_path)), model=EchoModelAdapter())
    for i in range(70):
        service.store.add(_document(f"版 {i} の内容。"))
    index = tmp_path / "index.jsonl"
    assert _records(index) == 70

    second = SidraService(settings=Settings(data_dir=str(tmp_path)), model=EchoModelAdapter())

    assert _records(index) == 1
    assert len(list(second.store.documents())) == 1
    # And what survived is the newest version, not an arbitrary one.
    assert "版 69" in list(second.store.documents())[0].content


def test_little_dead_weight_is_left_alone(tmp_path: Path) -> None:
    """Below the threshold the rewrite is not worth the risk of one."""

    service = SidraService(settings=Settings(data_dir=str(tmp_path)), model=EchoModelAdapter())
    for i in range(5):
        service.store.add(_document(f"版 {i}。"))
    index = tmp_path / "index.jsonl"

    SidraService(settings=Settings(data_dir=str(tmp_path)), model=EchoModelAdapter())

    assert _records(index) == 5


def test_the_compacted_file_keeps_its_permissions_and_reloads(tmp_path: Path) -> None:
    service = SidraService(settings=Settings(data_dir=str(tmp_path)), model=EchoModelAdapter())
    for i in range(70):
        service.store.add(_document(f"版 {i}。"))
    SidraService(settings=Settings(data_dir=str(tmp_path)), model=EchoModelAdapter())
    index = tmp_path / "index.jsonl"

    assert index.stat().st_mode & 0o077 == 0
    third = SidraService(settings=Settings(data_dir=str(tmp_path)), model=EchoModelAdapter())
    assert third.index_load_error == ""
    assert len(list(third.store.documents())) == 1


def test_no_temp_file_lingers(tmp_path: Path) -> None:
    service = SidraService(settings=Settings(data_dir=str(tmp_path)), model=EchoModelAdapter())
    for i in range(70):
        service.store.add(_document(f"版 {i}。"))
    SidraService(settings=Settings(data_dir=str(tmp_path)), model=EchoModelAdapter())

    assert not (tmp_path / "index.jsonl.compact").exists()


def test_a_pathless_store_compacts_to_nothing_quietly() -> None:
    assert DocumentStore().compact() == 0
