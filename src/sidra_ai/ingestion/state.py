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

    The state path itself is security-sensitive because redirecting it can
    silently move SHA/activity cursors to another local tree. Explicit parent
    traversal, symlinked path ancestry, symlinked final targets, and
    non-regular existing targets therefore fail closed before state is read or
    replaced.

    An existing state file is part of the correctness boundary. If it cannot
    be read or decoded, this store fails closed instead of silently replacing
    every repository cursor with a fresh empty state.
    """

    _LOCK_TIMEOUT_SECONDS = 5.0
    _LOCK_STALE_SECONDS = 30.0
    _LOCK_POLL_SECONDS = 0.01

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock_path = self.path.with_name(self.path.name + ".lock")

    def _reject_parent_traversal(self) -> None:
        if any(part == ".." for part in self.path.parts):
            raise StateStoreError(
                "ingestion state path contains explicit parent traversal"
            )

    def _assert_parent_ancestry_safe(self) -> None:
        """Reject symlink/non-directory components in existing parent ancestry."""

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
        """Reject an existing final target unless it is a regular file."""

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
        """Create missing parent directories without traversing known symlinks."""

        self._assert_parent_ancestry_safe()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StateStoreError(
                "ingestion state parent directory could not be created safely"
            ) from exc
        # Re-check after creation so a concurrent pathname change is not used
        # silently for the subsequent lock/temp-file operations.
        self._assert_parent_ancestry_safe()

    def _open_state_for_read(self):
        """Open an existing regular state file without following the final symlink."""

        self._assert_state_target_safe()
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        try:
            fd = os.open(self.path, flags)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StateStoreError(
                "persisted ingestion state could not be opened safely"
            ) from exc

        try:
            mode = os.fstat(fd).st_mode
            if not stat.S_ISREG(mode):
                raise StateStoreError(
                    "persisted ingestion state target is not a regular file"
                )
            # Re-check ancestry after opening. This does not replace a
            # descriptor-relative sandbox, but it fails closed on ordinary
            # symlink swaps rather than trusting pathname state once forever.
            self._assert_parent_ancestry_safe()
            return os.fdopen(fd, "r", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise

    def load(self) -> IngestionState:
        try:
            handle = self._open_state_for_read()
        except StateStoreError:
            raise

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
    def _locked_update(self) -> Iterator[None]:
        """Serialize state read-modify-write sequences across processes.

        ``os.mkdir`` is an atomic create on the filesystems SIDRA targets and
        works without an extra dependency. A crashed writer may leave an empty
        lock directory; after a conservative stale interval another worker can
        recover it. If a live writer does not finish within the short timeout,
        fail closed rather than risk a lost cursor update.
        """

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
                        # A live/non-empty lock must never be removed by force.
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

            # A final pathname check immediately before replace prevents a
            # pre-existing symlink/special file from being treated as a valid
            # cursor target. ``os.replace`` then atomically installs the
            # already-written regular temp file.
            self._assert_parent_ancestry_safe()
            self._assert_state_target_safe()
            os.replace(handle.name, self.path)
            self._assert_state_target_safe()
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
