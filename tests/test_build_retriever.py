"""The factory that decides which retriever the product runs.

The semantic pass was approved, implemented, measured - and unreachable: the
service constructed plain BM25 directly while ``SIDRA_EMBEDDING_MODEL_PATH``
sat unread in settings. These tests pin the wiring so an approved capability
cannot silently regress into dead configuration again, and so the no-weights
machine keeps getting the exact code path it always had.
"""

from __future__ import annotations

from types import SimpleNamespace

from sidra_ai.retrieval.embedding import EmbeddingRetriever, build_retriever
from sidra_ai.retrieval.search import BM25Retriever
from sidra_ai.security.gate import GatePolicy, SecurityGate
from sidra_ai.retrieval.store import DocumentStore


def _store() -> DocumentStore:
    return DocumentStore(SecurityGate(GatePolicy()))


def test_no_model_path_yields_plain_bm25() -> None:
    """Not an EmbeddingRetriever around an absent backend - plain BM25.

    The no-weights configuration is the v0.1 promise, and it must stay the
    same object it always was, not an equivalent-behaving wrapper whose
    equivalence someone now has to keep proving.
    """

    retriever = build_retriever(SimpleNamespace(embedding_model_path=""), _store())
    assert type(retriever) is BM25Retriever


def test_a_configured_path_yields_the_semantic_retriever(tmp_path) -> None:
    retriever = build_retriever(
        SimpleNamespace(
            embedding_model_path=str(tmp_path),
            embedding_query_prefix="query: ",
            embedding_passage_prefix="passage: ",
        ),
        _store(),
    )
    assert isinstance(retriever, EmbeddingRetriever)
    assert retriever.backend_name == "sentence-transformers"


def test_a_path_without_weights_degrades_ranking_not_availability(tmp_path) -> None:
    """An empty model directory must not take retrieval down.

    ``available()`` answers honestly and the retriever falls back to the
    lexical pass, because a missing model degrades ranking, never service.
    """

    retriever = build_retriever(
        SimpleNamespace(embedding_model_path=str(tmp_path)), _store()
    )
    assert retriever.semantic_enabled() is False
    assert retriever.search("なんでも", top_k=3) == []


def test_the_service_routes_through_the_factory(tmp_path) -> None:
    """SidraService must rank with the configured retriever, not its own.

    This is the exact hole being closed: settings carried the model path and
    the service ignored it.
    """

    from dataclasses import replace

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    base = replace(Settings(), data_dir=str(tmp_path / "data"))
    plain = SidraService(base, model=EchoModelAdapter())
    assert type(plain.retriever) is BM25Retriever

    configured = replace(
        base, embedding_model_path=str(tmp_path / "model")
    )
    semantic = SidraService(configured, model=EchoModelAdapter())
    assert isinstance(semantic.retriever, EmbeddingRetriever)
