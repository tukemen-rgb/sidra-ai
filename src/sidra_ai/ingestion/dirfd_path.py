"""Descriptor-relative local path helpers for ingestion cursor state.

This module is intentionally local-only. On POSIX runtimes with ``dir_fd``
and ``O_NOFOLLOW`` support, every parent component is opened relative to an
already-open directory descriptor. Reads, lock operations and atomic state
replacement can therefore share one stable parent descriptor across a complete
read-modify-write sequence instead of re-resolving pathnames between steps.
"""

from __future__ import annotations

import os
import secrets
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class DirFdPathError(RuntimeError):
    """Raised when an ingestion-state path cannot be opened safely."""


def supports_secure_dirfd() -> bool:
    supports = getattr(os, "supports_dir_fd", ())
    return (
        os.name != "nt"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in supports
        and os.mkdir in supports
        and os.rmdir in supports
        and os.stat in supports
        and os.rename in supports
        and os.unlink in supports
    )


def path_components(path: Path) -> tuple[str, ...]:
    if any(part == ".." for part in path.parts):
        raise DirFdPathError("ingestion state path contains parent traversal")
    parts = path.parts[1:] if path.is_absolute() else path.parts
    components = tuple(part for part in parts if part not in {"", "."})
    if not components:
        raise DirFdPathError("ingestion state path must name a file")
    return components


def directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_child(parent_fd: int, component: str, *, create: bool) -> int:
    flags = directory_flags()
    try:
        return os.open(component, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(component, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        return os.open(component, flags, dir_fd=parent_fd)


@contextmanager
def trusted_parent(path: Path, *, create: bool) -> Iterator[tuple[int, str] | None]:
    """Yield ``(parent_fd, final_name)`` without re-resolving parent components."""

    components = path_components(path)
    base = path.anchor if path.is_absolute() else "."
    try:
        parent_fd = os.open(base, directory_flags())
    except OSError as exc:
        raise DirFdPathError("ingestion state root could not be opened") from exc

    try:
        for component in components[:-1]:
            try:
                child_fd = _open_child(parent_fd, component, create=create)
            except FileNotFoundError:
                yield None
                return
            except OSError as exc:
                raise DirFdPathError("ingestion state parent could not be opened") from exc
            os.close(parent_fd)
            parent_fd = child_fd
        yield parent_fd, components[-1]
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass


def _assert_regular_or_missing(parent_fd: int, name: str) -> bool:
    try:
        mode = os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise DirFdPathError("ingestion state target could not be inspected") from exc
    if stat.S_ISLNK(mode):
        raise DirFdPathError("ingestion state target is a symlink")
    if not stat.S_ISREG(mode):
        raise DirFdPathError("ingestion state target is not a regular file")
    return True


def open_regular_read_at(parent_fd: int, name: str) -> int | None:
    """Open a state file relative to an already-trusted parent descriptor."""

    if not _assert_regular_or_missing(parent_fd, name):
        return None
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DirFdPathError("ingestion state could not be opened") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise DirFdPathError("ingestion state target is not a regular file")
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_regular_read(path: Path) -> int | None:
    with trusted_parent(path, create=False) as trusted:
        if trusted is None:
            return None
        return open_regular_read_at(*trusted)


def atomic_replace_bytes_at(parent_fd: int, final_name: str, payload: bytes) -> None:
    """Atomically replace a state file relative to a stable trusted parent fd."""

    _assert_regular_or_missing(parent_fd, final_name)
    temp_name = ""
    temp_fd: int | None = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        for _ in range(10):
            candidate = f".{final_name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
            try:
                temp_fd = os.open(candidate, flags, 0o600, dir_fd=parent_fd)
            except FileExistsError:
                continue
            temp_name = candidate
            break
        if temp_fd is None:
            raise DirFdPathError("could not allocate ingestion state temp file")

        with os.fdopen(temp_fd, "wb", closefd=True) as handle:
            temp_fd = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), 0o600)

        _assert_regular_or_missing(parent_fd, final_name)
        try:
            os.rename(
                temp_name,
                final_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
        except OSError as exc:
            raise DirFdPathError("ingestion state could not be replaced") from exc
        temp_name = ""
        if not _assert_regular_or_missing(parent_fd, final_name):
            raise DirFdPathError("ingestion state disappeared after replacement")
    finally:
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except OSError:
                pass
        if temp_name:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def atomic_replace_bytes(path: Path, payload: bytes) -> None:
    with trusted_parent(path, create=True) as trusted:
        assert trusted is not None
        atomic_replace_bytes_at(*trusted, payload)


def _assert_lock_directory(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DirFdPathError("ingestion state lock could not be inspected") from exc
    if stat.S_ISLNK(info.st_mode):
        raise DirFdPathError("ingestion state lock is a symlink")
    if not stat.S_ISDIR(info.st_mode):
        raise DirFdPathError("ingestion state lock is not a directory")
    return info


@contextmanager
def state_lock(
    path: Path,
    *,
    timeout_seconds: float,
    stale_seconds: float,
    poll_seconds: float,
) -> Iterator[tuple[int, str]]:
    """Hold a lock and yield the same trusted parent fd for the whole update."""

    with trusted_parent(path, create=True) as trusted:
        assert trusted is not None
        parent_fd, state_name = trusted
        lock_name = state_name + ".lock"
        deadline = time.monotonic() + timeout_seconds

        while True:
            try:
                os.mkdir(lock_name, 0o700, dir_fd=parent_fd)
                _assert_lock_directory(parent_fd, lock_name)
                break
            except FileExistsError:
                info = _assert_lock_directory(parent_fd, lock_name)
                if info is None:
                    continue
                if time.time() - info.st_mtime >= stale_seconds:
                    try:
                        os.rmdir(lock_name, dir_fd=parent_fd)
                    except FileNotFoundError:
                        pass
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for ingestion state lock: {path}")
                time.sleep(poll_seconds)
            except OSError as exc:
                raise DirFdPathError("ingestion state lock could not be created") from exc

        try:
            yield parent_fd, state_name
        finally:
            try:
                os.rmdir(lock_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
