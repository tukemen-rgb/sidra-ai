"""The retrieval index.

The store is the last line of defense before content becomes retrievable.
:meth:`DocumentStore.add` refuses a document that:

* is missing any provenance field,
* did not come back ``ALLOW`` from the security gate, or
* still contains credential-shaped material after redaction.

The third check is deliberate duplication. The gate already redacts; the
store re-checks because "a secret reached the index" is the failure mode
worth paying twice to prevent.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from sidra_ai.documents import Chunk, Document, is_instruction_authority
from sidra_ai.retrieval.chunker import chunk_document
from sidra_ai.security.decisions import Decision, GateResult
from sidra_ai.security.gate import SecurityGate


class SecretLeakError(RuntimeError):
    """Raised when content reaching the index still looks like a credential."""


class UnscreenedContentError(RuntimeError):
    """Raised when content is offered to the index without a gate verdict."""


class DocumentStore:
    """In-memory index with optional JSONL persistence.

    v0.1 keeps everything in process memory: the corpus is a handful of
    repositories, and an in-memory index avoids standing up a database
    before the retrieval design has settled. The interface is narrow enough
    that swapping in sqlite/FAISS later touches only this file.
    """

    def __init__(
        self,
        gate: SecurityGate | None = None,
        *,
        path: str | os.PathLike[str] | None = None,
    ) -> None:
        self._gate = gate
        self._path = Path(path) if path else None
        self._lock = threading.RLock()
        self._documents: dict[str, Document] = {}
        self._chunks: dict[str, Chunk] = {}
        self._chunks_by_document: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    def add(self, document: Document, *, gate_result: GateResult | None = None) -> str:
        """Index ``document``. Raises rather than indexing anything unsafe."""

        document.provenance.validate()

        if is_instruction_authority(document.provenance.trust_level):
            raise UnscreenedContentError(
                f"refusing to index {document.provenance.citation}: trust level "
                f"{document.provenance.trust_level.value!r} would make retrieved "
                "content an instruction authority"
            )

        if gate_result is None:
            if self._gate is None:
                raise UnscreenedContentError(
                    "documents must be screened by the security gate before "
                    "indexing; pass gate_result or construct the store with a gate"
                )
            gate_result, screened = self._gate.screen_document(document)
            if screened is None:
                raise UnscreenedContentError(
                    f"gate decision {gate_result.decision.value!r} for "
                    f"{document.provenance.citation}: not indexable"
                )
            document = screened

        if gate_result.decision is not Decision.ALLOW:
            raise UnscreenedContentError(
                f"gate decision {gate_result.decision.value!r} for "
                f"{document.provenance.citation}: only ALLOW may be indexed"
            )

        gate = self._gate or SecurityGate()
        if gate.contains_secret(document.content):
            raise SecretLeakError(
                f"refusing to index {document.provenance.citation}: content still "
                "matches a credential pattern after redaction"
            )

        with self._lock:
            doc_id = document.doc_id
            self._documents[doc_id] = document
            for chunk_id in self._chunks_by_document.pop(doc_id, []):
                self._chunks.pop(chunk_id, None)

            chunk_ids: list[str] = []
            for chunk in chunk_document(document):
                self._chunks[chunk.chunk_id] = chunk
                chunk_ids.append(chunk.chunk_id)
            self._chunks_by_document[doc_id] = chunk_ids

            if self._path is not None:
                self._append(document)
            return doc_id

    def add_all(
        self, documents: Iterable[Document], *, gate_result: GateResult | None = None
    ) -> list[str]:
        return [self.add(d, gate_result=gate_result) for d in documents]

    # ------------------------------------------------------------------
    def _append(self, document: Document) -> None:
        assert self._path is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch(mode=0o600)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(document.to_dict(), ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._documents)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def documents(self) -> Sequence[Document]:
        with self._lock:
            return tuple(self._documents.values())

    def chunks(self) -> Sequence[Chunk]:
        with self._lock:
            return tuple(self._chunks.values())

    def __iter__(self) -> Iterator[Chunk]:
        return iter(self.chunks())

    def get(self, doc_id: str) -> Document | None:
        return self._documents.get(doc_id)

    def by_repository(self, repository: str) -> Sequence[Document]:
        key = repository.lower()
        return tuple(
            d for d in self.documents() if d.provenance.repository.lower() == key
        )

    def clear(self) -> None:
        with self._lock:
            self._documents.clear()
            self._chunks.clear()
            self._chunks_by_document.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            repositories: dict[str, int] = {}
            source_types: dict[str, int] = {}
            redacted = 0
            for document in self._documents.values():
                repositories[document.provenance.repository] = (
                    repositories.get(document.provenance.repository, 0) + 1
                )
                key = document.provenance.source_type.value
                source_types[key] = source_types.get(key, 0) + 1
                redacted += 1 if document.redacted else 0
            return {
                "documents": len(self._documents),
                "chunks": len(self._chunks),
                "redacted_documents": redacted,
                "repositories": repositories,
                "source_types": source_types,
            }
