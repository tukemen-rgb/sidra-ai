"""Per-repository ingestion state.

The state file records the last commit SHA SIDRA ingested for each
repository. On the next run the client asks GitHub for HEAD; if it matches,
the pipeline stops immediately - no content is fetched, nothing is chunked,
and **no model is invoked**. That is the mechanism that keeps idle polling
free.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


@dataclass
class RepositoryState:
    """What we know about one repository's last ingestion."""

    repository: str
    last_commit_sha: str = ""
    last_ingested_at: str = ""
    """ISO-8601 UTC. Used as the ``since`` cursor for issues/PRs."""

    default_branch: str = ""
    license: str = "unknown"
    document_count: int = 0
    quarantined_count: int = 0
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepositoryState":
        known = {f: data.get(f) for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)  # type: ignore[arg-type]


@dataclass
class IngestionState:
    """State for every repository, persisted as one JSON document."""

    version: int = 1
    repositories: dict[str, RepositoryState] = field(default_factory=dict)

    def get(self, repository: str) -> RepositoryState:
        if repository not in self.repositories:
            self.repositories[repository] = RepositoryState(repository=repository)
        return self.repositories[repository]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "repositories": {k: v.to_dict() for k, v in self.repositories.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngestionState":
        return cls(
            version=int(data.get("version", 1)),
            repositories={
                key: RepositoryState.from_dict(value)
                for key, value in (data.get("repositories") or {}).items()
            },
        )


class StateStore:
    """Loads and atomically saves :class:`IngestionState`.

    Atomic replacement prevents torn JSON files, while a tiny cross-process
    lock around read-modify-write updates prevents two repository workers from
    overwriting each other's cursor state. The lock contains no state or
    credentials and is held only for the local file update.
    """

    _LOCK_TIMEOUT_SECONDS = 5.0
    _LOCK_STALE_SECONDS = 30.0
    _LOCK_POLL_SECONDS = 0.01

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock_path = self.path.with_name(self.path.name + ".lock")

    def load(self) -> IngestionState:
        if not self.path.exists():
            return IngestionState()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                return IngestionState.from_dict(json.load(handle))
        except (json.JSONDecodeError, OSError):
            # A corrupt state file must not wedge ingestion; the worst case
            # is one full re-ingest, which is idempotent.
            return IngestionState()

    @contextmanager
    def _locked_update(self) -> Iterator[None]:
        """Serialize state read-modify-write sequences across processes.

        ``os.mkdir`` is an atomic create on the filesystems SIDRA targets and
        works without an extra dependency. A crashed writer may leave an empty
        lock directory; after a conservative stale interval another worker can
        recover it. If a live writer does not finish within the short timeout,
        fail closed rather than risk a lost cursor update.
        """

        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self._LOCK_TIMEOUT_SECONDS

        while True:
            try:
                os.mkdir(self._lock_path)
                break
            except FileExistsError:
                try:
                    age = time.time() - self._lock_path.stat().st_mtime
                except FileNotFoundError:
                    continue

                if age >= self._LOCK_STALE_SECONDS:
                    try:
                        os.rmdir(self._lock_path)
                    except (FileNotFoundError, OSError):
                        pass
                    continue

                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"timed out waiting for ingestion state lock: {self._lock_path}"
                    )
                time.sleep(self._LOCK_POLL_SECONDS)

        try:
            yield
        finally:
            try:
                os.rmdir(self._lock_path)
            except FileNotFoundError:
                pass

    def _save_unlocked(self, state: IngestionState) -> None:
        """Persist ``state``; caller must hold ``_locked_update`` when merging."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=self.path.name + ".",
            suffix=".tmp",
            delete=False,
        )
        try:
            with handle:
                json.dump(state.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(handle.name, self.path)
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise

    def save(self, state: IngestionState) -> None:
        """Atomically replace state while excluding concurrent writers."""

        with self._locked_update():
            self._save_unlocked(state)

    def mark_ingested(
        self,
        repository: str,
        *,
        commit_sha: str,
        document_count: int,
        quarantined_count: int = 0,
        default_branch: str = "",
        license: str = "unknown",
    ) -> IngestionState:
        with self._locked_update():
            state = self.load()
            record = state.get(repository)
            record.last_commit_sha = commit_sha
            record.last_ingested_at = datetime.now(timezone.utc).isoformat()
            record.document_count = document_count
            record.quarantined_count = quarantined_count
            record.last_error = ""
            if default_branch:
                record.default_branch = default_branch
            if license:
                record.license = license
            self._save_unlocked(state)
            return state

    def mark_error(self, repository: str, message: str) -> IngestionState:
        with self._locked_update():
            state = self.load()
            state.get(repository).last_error = message[:500]
            self._save_unlocked(state)
            return state
