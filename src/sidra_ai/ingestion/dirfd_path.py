"""Descriptor-relative local path helpers for ingestion cursor state.

This module is intentionally local-only.  On POSIX runtimes with dir-fd
support, it walks each directory component relative to an already-open parent
and refuses symlinks via ``O_NOFOLLOW``.  Callers can therefore keep a stable
parent descriptor across state read/write operations instead of checking a
pathname and later re-resolving it.
"""

from __future__ import annotations

import os
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
    """Yield ``(parent_fd, final_name)`` without re-resolving parent components.

    ``None`` is yielded only when ``create`` is false and a parent does not
    exist.  Any symlink/non-directory encountered during the walk fails closed.
    """

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
