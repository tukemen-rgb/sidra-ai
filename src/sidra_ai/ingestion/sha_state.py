"""Minimal, secret-free repository SHA state for incremental ingestion.

The state store intentionally persists only repository identity, the last
successfully ingested commit SHA, and a timestamp. It never stores GitHub
tokens, document content, prompts, or credentials.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile
from typing import Optional

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class InvalidRepository(ValueError):
    """Raised when a repository name is not in owner/name form."""


class InvalidCommitSha(ValueError):
    """Raised when a commit SHA is not a full 40-character hex digest."""


class ConcurrentStateUpdate(RuntimeError):
    """Raised when compare-and-set detects a stale ingestion worker."""


@dataclass(frozen=True)
class RepoSyncState:
    repository: str
    last_commit_sha: str
    updated_at: str


@dataclass(frozen=True)
class SyncDecision:
    repository: str
    previous_sha: Optional[str]
    head_sha: str
    changed: bool


class ShaStateStore:
    """File-backed compare-and-set state for repository ingestion.

    Each repository is stored in its own JSON file. Writes use an atomic
    replace so a process interruption cannot leave a partially-written state
    file. ``advance`` additionally performs compare-and-set against the
    previous SHA, which prevents concurrent ingestion workers from silently
    overwriting newer state.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, repository: str) -> Optional[RepoSyncState]:
        repository = _validate_repository(repository)
        path = self._path_for(repository)
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        state = RepoSyncState(
            repository=_validate_repository(str(payload["repository"])),
            last_commit_sha=_validate_sha(str(payload["last_commit_sha"])),
            updated_at=str(payload["updated_at"]),
        )
        if state.repository != repository:
            raise ValueError("state repository does not match requested repository")
        return state

    def decide(self, repository: str, head_sha: str) -> SyncDecision:
        repository = _validate_repository(repository)
        head_sha = _validate_sha(head_sha)
        current = self.get(repository)
        previous_sha = current.last_commit_sha if current else None
        return SyncDecision(
            repository=repository,
            previous_sha=previous_sha,
            head_sha=head_sha,
            changed=previous_sha != head_sha,
        )

    def advance(
        self,
        repository: str,
        new_sha: str,
        *,
        expected_previous_sha: Optional[str],
    ) -> RepoSyncState:
        """Persist a successfully ingested SHA using compare-and-set.

        Call this only *after* the corresponding ingestion operation has
        completed successfully. ``expected_previous_sha`` must be the SHA
        observed before ingestion (or ``None`` for first sync).
        """

        repository = _validate_repository(repository)
        new_sha = _validate_sha(new_sha)
        if expected_previous_sha is not None:
            expected_previous_sha = _validate_sha(expected_previous_sha)

        current = self.get(repository)
        actual_previous_sha = current.last_commit_sha if current else None
        if actual_previous_sha != expected_previous_sha:
            raise ConcurrentStateUpdate(
                "repository state changed after the ingestion decision; "
                "refuse to overwrite newer state"
            )

        state = RepoSyncState(
            repository=repository,
            last_commit_sha=new_sha,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._atomic_write(self._path_for(repository), asdict(state))
        return state

    def _path_for(self, repository: str) -> Path:
        owner, name = repository.split("/", 1)
        return self.root / f"{owner}__{name}.json"

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, str]) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, sort_keys=True)
            tmp.write("\n")
            tmp.flush()
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)


def _validate_repository(repository: str) -> str:
    if not _REPOSITORY_RE.fullmatch(repository):
        raise InvalidRepository("repository must be in owner/name form")
    owner, name = repository.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise InvalidRepository("repository owner/name cannot be dot path segments")
    return repository


def _validate_sha(sha: str) -> str:
    if not _SHA_RE.fullmatch(sha):
        raise InvalidCommitSha("commit SHA must be a full 40-character hex digest")
    return sha.lower()
