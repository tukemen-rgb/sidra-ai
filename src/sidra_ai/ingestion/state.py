"""Per-repository ingestion state.

The state file records the last commit SHA SIDRA ingested for each
repository. It is also the cursor for mutable PR/Issue polling, so the file is
part of the RAG freshness and correctness boundary. A damaged or redirected
state path must fail closed rather than reset or move repository cursors.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sidra_ai.ingestion.dirfd_path import (
    DirFdPathError,
    atomic_replace_bytes,
    atomic_replace_bytes_at,
    open_regular_read,
    open_regular_read_at,
    state_lock,
    supports_secure_dirfd,
)


class StateStoreError(RuntimeError):
    """Raised when persisted ingestion cursor state cannot be trusted."""


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
        if "version" not in data:
            raise ValueError("persisted ingestion state is missing its schema version")
        version = data["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version != 1:
            raise ValueError("persisted ingestion state has an unsupported schema version")

        if "repositories" not in data or not isinstance(data["repositories"], dict):
            raise ValueError("persisted ingestion state is missing its repository map")

        return cls(
            version=version,
            repositories={
                key: RepositoryState.from_dict(value)
                for key, value in data["repositories"].items()
            },
        )


class StateStore:
    """Loads and atomically saves :class:`IngestionState`.

    The state path is part of the RAG freshness/correctness boundary. On
    supported POSIX runtimes, reads, lock acquisition, temp-file creation and
    atomic replacement are performed relative to trusted directory descriptors
    so an ancestor cannot be swapped after a pathname check. Other platforms
    retain a conservative pathname fallback.

    An existing state file is never silently reset when it is unreadable or
    malformed.
    """

    _LOCK_TIMEOUT_SECONDS = 5.0
    _LOCK_STALE_SECONDS = 30.0
    _LOCK_POLL_SECONDS = 0.01

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock_path = self.path.with_name(self.path.name + ".lock")

    @staticmethod
    def _supports_secure_dirfd() -> bool:
        return supports_secure_dirfd()

    def _reject_parent_traversal(self) -> None:
        if any(part == ".." for part in self.path.parts):
            raise StateStoreError(
                "ingestion state path contains explicit parent traversal"
            )

    def _assert_parent_ancestry_safe(self) -> None:
        self._reject_parent_traversal()
        current = Path(os.path.abspath(os.fspath(self.path.parent)))
        while True:
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise StateStoreError(
                    "ingestion state parent ancestry could not be inspected"
                ) from exc
            else:
                if stat.S_ISLNK(mode):
                    raise StateStoreError(
                        "ingestion state parent ancestry contains a symlink"
                    )
                if not stat.S_ISDIR(mode):
                    raise StateStoreError(
                        "ingestion state parent ancestry contains a non-directory"
                    )
            parent = current.parent
            if parent == current:
                break
            current = parent

    def _assert_state_target_safe(self) -> None:
        self._assert_parent_ancestry_safe()
        try:
            mode = self.path.lstat().st_mode
        except FileNotFoundError:
            return
        except OSError as exc:
            raise StateStoreError(
                "persisted ingestion state target could not be inspected"
            ) from exc
        if stat.S_ISLNK(mode):
            raise StateStoreError("persisted ingestion state target is a symlink")
        if not stat.S_ISREG(mode):
            raise StateStoreError(
                "persisted ingestion state target is not a regular file"
            )

    def _prepare_parent_directory(self) -> None:
        self._assert_parent_ancestry_safe()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StateStoreError(
                "ingestion state parent directory could not be created safely"
            ) from exc
        self._assert_parent_ancestry_safe()

    def _open_state_for_read_fallback(self):
        self._assert_state_target_safe()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.path, flags)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StateStoreError(
                "persisted ingestion state could not be opened safely"
            ) from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise StateStoreError(
                    "persisted ingestion state target is not a regular file"
                )
            self._assert_parent_ancestry_safe()
            return os.fdopen(fd, "r", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise

    def _open_state_for_read(self, trusted: tuple[int, str] | None = None):
        if trusted is not None:
            try:
                fd = open_regular_read_at(*trusted)
            except DirFdPathError as exc:
                raise StateStoreError(str(exc)) from exc
            if fd is None:
                return None
            return os.fdopen(fd, "r", encoding="utf-8")

        if self._supports_secure_dirfd():
            try:
                fd = open_regular_read(self.path)
            except DirFdPathError as exc:
                raise StateStoreError(str(exc)) from exc
            if fd is None:
                return None
            return os.fdopen(fd, "r", encoding="utf-8")
        return self._open_state_for_read_fallback()

    def _load_unlocked(
        self,
        trusted: tuple[int, str] | None = None,
    ) -> IngestionState:
        handle = self._open_state_for_read(trusted)
        if handle is None:
            return IngestionState()
        try:
            with handle:
                raw = json.load(handle)
        except json.JSONDecodeError as exc:
            raise StateStoreError(
                "persisted ingestion state is invalid JSON; refusing to reset cursors"
            ) from exc
        except OSError as exc:
            raise StateStoreError(
                "persisted ingestion state could not be read; refusing to reset cursors"
            ) from exc
        if not isinstance(raw, dict):
            raise StateStoreError(
                "persisted ingestion state has an invalid top-level shape"
            )
        try:
            return IngestionState.from_dict(raw)
        except (AttributeError, TypeError, ValueError) as exc:
            raise StateStoreError(
                "persisted ingestion state has an invalid schema"
            ) from exc

    def load(self) -> IngestionState:
        return self._load_unlocked()

    def _assert_lock_path_safe_if_present(self) -> None:
        try:
            mode = self._lock_path.lstat().st_mode
        except FileNotFoundError:
            return
        except OSError as exc:
            raise StateStoreError(
                "ingestion state lock path could not be inspected"
            ) from exc
        if stat.S_ISLNK(mode):
            raise StateStoreError("ingestion state lock path is a symlink")
        if not stat.S_ISDIR(mode):
            raise StateStoreError("ingestion state lock path is not a directory")

    @contextmanager
    def _locked_update_fallback(self) -> Iterator[None]:
        self._prepare_parent_directory()
        deadline = time.monotonic() + self._LOCK_TIMEOUT_SECONDS
        while True:
            try:
                os.mkdir(self._lock_path)
                self._assert_parent_ancestry_safe()
                self._assert_lock_path_safe_if_present()
                break
            except FileExistsError:
                self._assert_parent_ancestry_safe()
                self._assert_lock_path_safe_if_present()
                try:
                    age = time.time() - self._lock_path.lstat().st_mtime
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise StateStoreError(
                        "ingestion state lock path could not be inspected"
                    ) from exc
                if age >= self._LOCK_STALE_SECONDS:
                    try:
                        os.rmdir(self._lock_path)
                    except FileNotFoundError:
                        pass
                    except OSError:
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

    @contextmanager
    def _locked_update(self) -> Iterator[tuple[int, str] | None]:
        if self._supports_secure_dirfd():
            try:
                with state_lock(
                    self.path,
                    timeout_seconds=self._LOCK_TIMEOUT_SECONDS,
                    stale_seconds=self._LOCK_STALE_SECONDS,
                    poll_seconds=self._LOCK_POLL_SECONDS,
                ) as trusted:
                    yield trusted
            except DirFdPathError as exc:
                raise StateStoreError(str(exc)) from exc
            return
        with self._locked_update_fallback():
            yield None

    def _save_unlocked_fallback(self, state: IngestionState) -> None:
        self._prepare_parent_directory()
        self._assert_state_target_safe()
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
                if hasattr(os, "fchmod"):
                    os.fchmod(handle.fileno(), 0o600)
            self._assert_parent_ancestry_safe()
            self._assert_state_target_safe()
            os.replace(handle.name, self.path)
            self._assert_state_target_safe()
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise

    def _save_unlocked(
        self,
        state: IngestionState,
        trusted: tuple[int, str] | None = None,
    ) -> None:
        if self._supports_secure_dirfd():
            payload = json.dumps(
                state.to_dict(),
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")
            try:
                if trusted is None:
                    atomic_replace_bytes(self.path, payload)
                else:
                    atomic_replace_bytes_at(*trusted, payload)
            except DirFdPathError as exc:
                raise StateStoreError(str(exc)) from exc
            return
        self._save_unlocked_fallback(state)

    def save(self, state: IngestionState) -> None:
        with self._locked_update() as trusted:
            self._save_unlocked(state, trusted)

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
        with self._locked_update() as trusted:
            state = self._load_unlocked(trusted)
            record = state.get(repository)
            record.last_commit_sha = commit_sha
            record.last_ingested_at = datetime.now(timezone.utc).isoformat()
            record.document_count = document_count
            record.quarantined_count = quarantined_count
            record.last_error = ""
            if default_branch:
                record.default_branch = default_branch
            if license:
                record.license = license_id
            self._save_unlocked(state, trusted)
            return state

    def mark_error(self, repository: str, message: str) -> IngestionState:
        with self._locked_update() as trusted:
            state = self._load_unlocked(trusted)
            state.get(repository).last_error = message[:500]
            self._save_unlocked(state, trusted)
            return state
