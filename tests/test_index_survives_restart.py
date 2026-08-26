"""The index has to still be there after the process restarts.

Measured 2026-08-26 against a data directory holding 484 documents from five
repositories: a fresh process started with **zero**, while ``state.json`` still
reported every repository as ingested. Nothing was corrupt - re-running the
analyze endpoint rebuilt it correctly - but until it was re-run, every
question was answered with no evidence at all.

The cause was not a missing feature. ``DocumentStore`` already appended each
document and already had a ``load()`` that puts every record back through the
current security gate. No caller in the project ever passed it a path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.models.echo import EchoModelAdapter
from datetime import datetime, timezone


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=str(tmp_path))


def _document(text: str, path: str) -> Document:
    return Document(
        content=text,
        provenance=Provenance(
            source="github",
            repository="tukemen-rgb/site",
            path=path,
            commit_sha="a" * 40,
            timestamp=datetime(2026, 8, 26, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


def test_a_second_service_finds_what_the_first_indexed(tmp_path: Path) -> None:
    first = SidraService(settings=_settings(tmp_path), model=EchoModelAdapter())
    first.store.add(_document("投稿できるファイルは 200MB までです。", "docs/upload.md"))

    second = SidraService(settings=_settings(tmp_path), model=EchoModelAdapter())

    assert len(list(second.store.documents())) == 1
    assert second.retriever.search("ファイルの上限", top_k=1)


def test_the_index_file_is_not_world_readable(tmp_path: Path) -> None:
    """It holds indexed repository content, so it gets the same 0600 as the rest."""

    service = SidraService(settings=_settings(tmp_path), model=EchoModelAdapter())
    service.store.add(_document("社外に出さない内容。", "docs/x.md"))

    index = tmp_path / "index.jsonl"
    assert index.is_file()
    assert index.stat().st_mode & 0o077 == 0, oct(index.stat().st_mode)


def test_the_reload_is_reported_rather_than_assumed(tmp_path: Path) -> None:
    """'Empty' and 'failed to load' look identical from outside."""

    first = SidraService(settings=_settings(tmp_path), model=EchoModelAdapter())
    first.store.add(_document("何かの記録。", "docs/y.md"))

    second = SidraService(settings=_settings(tmp_path), model=EchoModelAdapter())

    assert second.index_load is not None
    assert second.index_load.loaded == 1
    assert second.index_load_error == ""


def test_an_unreadable_index_does_not_stop_the_service_starting(
    tmp_path: Path,
) -> None:
    """The operator can always re-ingest; a damaged file must not lock them out."""

    (tmp_path / "index.jsonl").write_text("{ this is not json\n", encoding="utf-8")

    service = SidraService(settings=_settings(tmp_path), model=EchoModelAdapter())

    assert list(service.store.documents()) == []
    # A torn line is skipped and counted, not raised - so this is a clean load
    # that found nothing, and the count is what says so.
    assert service.index_load is not None
    assert service.index_load.unreadable == 1
