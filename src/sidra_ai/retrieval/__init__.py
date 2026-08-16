"""Retrieval: chunking, indexing and search, all provenance-preserving."""

from sidra_ai.retrieval.chunker import chunk_document
from sidra_ai.retrieval.search import (
    BM25Retriever,
    Retriever,
    SearchResult,
    tokenize,
)
from sidra_ai.retrieval.store import (
    DocumentStore,
    SecretLeakError,
    UnscreenedContentError,
)

__all__ = [
    "BM25Retriever",
    "DocumentStore",
    "Retriever",
    "SearchResult",
    "SecretLeakError",
    "UnscreenedContentError",
    "chunk_document",
    "tokenize",
]
