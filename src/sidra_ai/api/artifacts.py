"""Listing and handing back the files SIDRA generated.

Two things an operator needs after "作って": to see that something was made,
and to open it. Both are served from one directory, ``<data_dir>/artifacts``,
and nothing else on the disk is reachable through them.

The listing carries **names, sizes and times only**. A generated deck is
grounded in retrieved documents, so its body is DATA the same way the source
was; putting a preview in a listing would leak indexed content into a place
that looks like metadata. Anyone entitled to the body can ask for the file,
which is the same authenticated route with an explicit name.

A file is handed back as a download, never as a page in this origin. The
artifacts contain generated markup, and rendering that at ``/v1/artifacts/x``
would run it with the service's own origin - the one the operator's token is
typed into. ``Content-Disposition: attachment`` plus ``nosniff`` keeps a
generated document a document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

#: Exactly what the generators produce. A name is validated against this
#: *before* it is joined to anything, so traversal never becomes a question
#: about how the filesystem resolves ``..``.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")

MAX_LISTED = 200


class ArtifactNotFound(Exception):
    """No such artifact, or a name that was never allowed to be one."""


@dataclass(frozen=True)
class Artifact:
    name: str
    bytes: int
    modified: str

    def to_dict(self) -> dict:
        return {"name": self.name, "bytes": self.bytes, "modified": self.modified}


def artifacts_dir(data_dir: str | Path) -> Path:
    return Path(data_dir) / "artifacts"


def list_artifacts(data_dir: str | Path) -> list[Artifact]:
    """Newest first. A missing directory is an empty list, not an error."""

    directory = artifacts_dir(data_dir)
    if not directory.is_dir():
        return []
    found = []
    for path in directory.iterdir():
        # Symlinks are skipped rather than followed: a link planted in the
        # artifacts directory is the one way this listing could name a file
        # outside it.
        if not path.is_file() or path.is_symlink():
            continue
        if not SAFE_NAME.match(path.name):
            continue
        stat = path.stat()
        found.append(
            Artifact(
                path.name,
                stat.st_size,
                datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
            )
        )
    found.sort(key=lambda a: (a.modified, a.name), reverse=True)
    return found[:MAX_LISTED]


def read_artifact(data_dir: str | Path, name: str) -> tuple[bytes, str]:
    """Return one artifact's bytes and its name, or raise ``ArtifactNotFound``.

    Both checks are kept: the name pattern rejects traversal syntax, and the
    resolved path is required to sit inside the directory. The second catches
    what the first cannot - a symlink whose own name is perfectly ordinary.
    """

    if not SAFE_NAME.match(name or ""):
        raise ArtifactNotFound(name)
    directory = artifacts_dir(data_dir).resolve()
    path = (directory / name).resolve()
    if not path.is_file() or directory not in path.parents:
        raise ArtifactNotFound(name)
    return path.read_bytes(), path.name


__all__ = [
    "Artifact",
    "ArtifactNotFound",
    "MAX_LISTED",
    "SAFE_NAME",
    "artifacts_dir",
    "list_artifacts",
    "read_artifact",
]
