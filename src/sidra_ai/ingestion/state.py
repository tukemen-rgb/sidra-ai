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
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    """Loads and atomically saves :class:`IngestionState`."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

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

    def save(self, state: IngestionState) -> None:
        """Write via a temp file + rename so a crash cannot truncate state."""

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
        self.save(state)
        return state

    def mark_error(self, repository: str, message: str) -> IngestionState:
        state = self.load()
        state.get(repository).last_error = message[:500]
        self.save(state)
        return state
