"""The retrieval index.

The store is the last line of defense before content becomes retrievable.
:meth:`DocumentStore.add` refuses a document that:

* is missing any provenance field,
* did not come back ``ALLOW`` from the security gate, or
* still contains credential-shaped material after redaction.

The third check is deliberate duplication. The gate already redacts; the
store re-checks because "a secret reached the index" is the failure mode
worth paying twice to prevent.

For repository-backed knowledge, the store also enforces a *current-source*
view.  A new revision of the same logical source (origin + repository + source
type + path) retires older revisions before the new chunks become retrievable.
Deletion/quarantine paths can call :meth:`DocumentStore.retire_source`
explicitly.  This prevents an old, correctly cited document from continuing
to masquerade as current knowledge merely because its commit SHA differs.

Optional JSONL persistence is also a security boundary. On POSIX/Linux
runtimes with dir-fd support, every parent component is opened relative to an
already verified directory descriptor and the final regular file is opened
relative to that descriptor with ``O_NOFOLLOW``. This avoids re-resolving a
pathname after an ancestry check and closes ancestor symlink TOCTOU races.
Owner-only permissions are enforced through the opened file descriptor. A
persistence failure occurs before the in-memory index is mutated so a failed
write cannot silently retire the previously retrievable revision.
"""

from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from sidra_ai.documents import Chunk, Document, SourceType, is_instruction_authority
from sidra_ai.retrieval.chunker import chunk_document
from sidra_ai.security.decisions import Decision, GateResult
from sidra_ai.security.gate import SecurityGate


class SecretLeakError(RuntimeError):
    """Raised when content reaching the index still looks like a credential."""


class UnscreenedContentError(RuntimeError):
    """Raised when content is offered to the index without a gate verdict."""


class PersistencePathError(RuntimeError):
    """Raised when the optional local JSONL target cannot be trusted."""


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
    @staticmethod
    def _logical_source_key(document: Document) -> tuple[str, str, SourceType, str]:
        provenance = document.provenance
        return (
            provenance.source,
            provenance.repository.lower(),
            provenance.source_type,
            provenance.path,
        )

    def _remove_document_locked(self, doc_id: str) -> bool:
        """Remove one document and all of its chunks while ``_lock`` is held."""

        document = self._documents.pop(doc_id, None)
        if document is None:
            return False
        for chunk_id in self._chunks_by_document.pop(doc_id, []):
            self._chunks.pop(chunk_id, None)
        return True

    def _retire_logical_source_locked(
        self,
        logical_key: tuple[str, str, SourceType, str],
        *,
        keep_doc_id: str | None = None,
    ) -> int:
        retired = 0
        for doc_id, existing in tuple(self._documents.items()):
            if doc_id == keep_doc_id:
                continue
            if self._logical_source_key(existing) != logical_key:
                continue
            retired += 1 if self._remove_document_locked(doc_id) else 0
        return retired

    def add(self, document: Document, *, gate_result: GateResult | None = None) -> str:
        """Index ``document``. Raises rather than indexing anything unsafe.

        Once the candidate has passed every safety check, older revisions of
        the same logical source are retired under the same store lock before
        the new chunks become retrievable. Safety failures therefore never
        delete the previously indexed revision implicitly; ingestion must call
        :meth:`retire_source` explicitly when the upstream source was deleted
        or its newest revision is intentionally not retrievable.

        When optional JSONL persistence is enabled, chunking is prepared first
        and the append is completed before any in-memory retirement/mutation.
        A filesystem-boundary failure therefore leaves the previous index view
        intact instead of creating a state the persisted log did not record.
        """

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

        prepared_chunks = tuple(chunk_document(document))

        with self._lock:
            if self._path is not None:
                self._append(document)

            doc_id = document.doc_id
            logical_key = self._logical_source_key(document)
            self._retire_logical_source_locked(logical_key, keep_doc_id=doc_id)

            self._documents[doc_id] = document
            for chunk_id in self._chunks_by_document.pop(doc_id, []):
                self._chunks.pop(chunk_id, None)

            chunk_ids: list[str] = []
            for chunk in prepared_chunks:
                self._chunks[chunk.chunk_id] = chunk
                chunk_ids.append(chunk.chunk_id)
            self._chunks_by_document[doc_id] = chunk_ids
            return doc_id

    def add_all(
        self, documents: Iterable[Document], *, gate_result: GateResult | None = None
    ) -> list[str]:
        return [self.add(d, gate_result=gate_result) for d in documents]

    def retire_source(
        self,
        *,
        repository: str,
        path: str,
        source: str = "github",
        source_type: SourceType | None = None,
    ) -> int:
        """Remove retrievable revisions for one exact logical source.

        This is intentionally exact-match only: no glob, prefix, or repository-
        wide deletion is accepted. L3 ingestion can use it when GitHub reports
        a path deleted, or when the newest revision is BLOCK/QUARANTINE and an
        older revision must not remain retrievable as if it were current.

        Returns the number of retired document revisions.
        """

        repository = repository.strip()
        path = path.strip()
        source = source.strip()
        if not repository or "/" not in repository:
            raise ValueError("repository must be in 'owner/name' form")
        if not path:
            raise ValueError("path must not be empty")
        if not source:
            raise ValueError("source must not be empty")
        if source_type is not None and not isinstance(source_type, SourceType):
            raise TypeError("source_type must be a SourceType or None")

        key_repository = repository.lower()
        with self._lock:
            retired = 0
            for doc_id, document in tuple(self._documents.items()):
                provenance = document.provenance
                if provenance.source != source:
                    continue
                if provenance.repository.lower() != key_repository:
                    continue
                if provenance.path != path:
                    continue
                if source_type is not None and provenance.source_type is not source_type:
                    continue
                retired += 1 if self._remove_document_locked(doc_id) else 0
            return retired

    # ------------------------------------------------------------------
    @staticmethod
    def _reject_parent_traversal(path: Path) -> None:
        if ".." in path.parts:
            raise PersistencePathError(
                "refusing persistence path with parent traversal"
            )

    @staticmethod
    def _supports_secure_dirfd() -> bool:
        supports_dir_fd = getattr(os, "supports_dir_fd", ())
        return (
            os.name != "nt"
            and hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
            and os.open in supports_dir_fd
            and os.mkdir in supports_dir_fd
        )

    @staticmethod
    def _path_components(path: Path) -> tuple[str, ...]:
        DocumentStore._reject_parent_traversal(path)
        parts = path.parts[1:] if path.is_absolute() else path.parts
        components = tuple(part for part in parts if part not in {"", "."})
        if not components:
            raise PersistencePathError("persistence path must name a file")
        return components

    @staticmethod
    def _directory_flags() -> int:
        return (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )

    @staticmethod
    def _open_child_directory(parent_fd: int, component: str) -> int:
        flags = DocumentStore._directory_flags()
        try:
            return os.open(component, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            try:
                os.mkdir(component, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                # A concurrent creator won the race. Re-open with O_NOFOLLOW;
                # a symlink or non-directory therefore still fails closed.
                pass
            return os.open(component, flags, dir_fd=parent_fd)

    @staticmethod
    def _assert_no_symlink_ancestors(path: Path) -> None:
        """Best-effort fallback check for platforms without secure dirfd walking."""

        current = path
        while True:
            try:
                if current.is_symlink():
                    raise PersistencePathError(
                        "refusing persistence path through symlinked directory"
                    )
            except OSError as exc:
                raise PersistencePathError(
                    "could not inspect persistence directory"
                ) from exc

            parent = current.parent
            if parent == current:
                return
            current = parent

    def _open_persistence_fd_dirfd(self) -> int:
        """Open JSONL by walking every parent from already-trusted dirfds."""

        assert self._path is not None
        components = self._path_components(self._path)
        base = self._path.anchor if self._path.is_absolute() else "."

        try:
            parent_fd = os.open(base, self._directory_flags())
        except OSError as exc:
            raise PersistencePathError(
                "could not open persistence path root"
            ) from exc

        try:
            for component in components[:-1]:
                try:
                    child_fd = self._open_child_directory(parent_fd, component)
                except OSError as exc:
                    raise PersistencePathError(
                        "could not safely prepare persistence directory"
                    ) from exc
                os.close(parent_fd)
                parent_fd = child_fd

            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(components[-1], flags, 0o600, dir_fd=parent_fd)
            except OSError as exc:
                raise PersistencePathError(
                    "could not safely open persistence target"
                ) from exc

            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise PersistencePathError(
                        "persistence target must be a regular file"
                    )
                if hasattr(os, "fchmod"):
                    os.fchmod(fd, 0o600)
                return fd
            except BaseException:
                os.close(fd)
                raise
        finally:
            os.close(parent_fd)

    def _open_persistence_fd_fallback(self) -> int:
        """Best-effort fallback for runtimes without safe descriptor walking."""

        assert self._path is not None
        self._reject_parent_traversal(self._path)

        parent = self._path.parent
        self._assert_no_symlink_ancestors(parent)
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PersistencePathError(
                "could not prepare persistence directory"
            ) from exc
        self._assert_no_symlink_ancestors(parent)
        if self._path.is_symlink():
            raise PersistencePathError("refusing symlinked persistence target")

        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)

        try:
            fd = os.open(self._path, flags, 0o600)
        except OSError as exc:
            raise PersistencePathError(
                "could not safely open persistence target"
            ) from exc

        try:
            self._assert_no_symlink_ancestors(parent)
            if self._path.is_symlink():
                raise PersistencePathError("refusing symlinked persistence target")
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PersistencePathError(
                    "persistence target must be a regular file"
                )
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            else:  # pragma: no cover - Windows fallback
                os.chmod(self._path, 0o600, follow_symlinks=False)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _open_persistence_fd(self) -> int:
        """Open the JSONL target without pathname re-resolution on POSIX."""

        if self._supports_secure_dirfd():
            return self._open_persistence_fd_dirfd()
        return self._open_persistence_fd_fallback()

    def _append(self, document: Document) -> None:
        assert self._path is not None
        encoded = json.dumps(document.to_dict(), ensure_ascii=False) + "\n"
        fd = self._open_persistence_fd()
        try:
            with os.fdopen(fd, "a", encoding="utf-8", closefd=True) as handle:
                handle.write(encoded)
                handle.flush()
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

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
