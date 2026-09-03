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
        # Revision sidecars (C-1112) are read by the revise path's own glob,
        # never through this listing - and shown to an operator they doubled
        # every row and read as gibberish when clicked (C-1209). Hidden from
        # the listing only: the file stays on disk and stays downloadable by
        # name, so nothing that already points at one breaks.
        if path.name.endswith(".meta.json"):
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


#: Media types a download may declare. Only formats that cannot execute in
#: this origin get a real type; markup and vector formats (.html, .svg) are
#: deliberately absent and fall back to ``application/octet-stream``, because
#: with a correct type one misplaced ``Content-Disposition`` away they would
#: render beside the field the operator's token is typed into. Every download
#: still leaves as an attachment with sniffing disabled either way.
MEDIA_TYPES: dict[str, str] = {
    ".gif": "image/gif",
    ".png": "image/png",
    ".md": "text/markdown; charset=utf-8",
    ".obj": "text/plain; charset=utf-8",
    ".mtl": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".json": "application/json",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def media_type_for(name: str) -> str:
    """The Content-Type a file downloads with, decided by its extension.

    The default is the unknown-bytes type, not a guess: a wrong specific
    type misleads the program that opens the file, while octet-stream only
    costs the double-click association.
    """

    suffix = Path(name.lower()).suffix
    return MEDIA_TYPES.get(suffix, "application/octet-stream")


def projects_dir(data_dir: str | Path) -> Path:
    return artifacts_dir(data_dir) / "projects"


@dataclass(frozen=True)
class ProjectListing:
    """One production directory and the files inside it.

    Same contract as the flat listing: names, sizes and times, never content.
    ``files`` uses paths relative to the project (``scenario.md``,
    ``assets/player.svg``) so an operator can see the whole production at a
    glance and ask for any piece of it by exactly the name shown.
    """

    slug: str
    modified: str
    files: tuple[Artifact, ...]

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "modified": self.modified,
            "files": [artifact.to_dict() for artifact in self.files],
        }


def _stamp(path: Path) -> str:
    return (
        datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _project_files(root: Path) -> list[Artifact]:
    """Files of one project: the top level plus one ``assets`` level.

    Exactly the layout the scaffolder writes, and nothing deeper: a listing
    that walked arbitrarily would follow whatever a future generator happens
    to create, and its safety would depend on code it has never seen.
    Symlinks and unsafe names are skipped for the same reason as in the flat
    listing - a planted link is the one way out of the directory.
    """

    found: list[Artifact] = []
    candidates = list(root.iterdir())
    assets = root / "assets"
    if assets.is_dir() and not assets.is_symlink():
        candidates += list(assets.iterdir())
    for path in candidates:
        if not path.is_file() or path.is_symlink():
            continue
        if not SAFE_NAME.match(path.name):
            continue
        relative = str(path.relative_to(root))
        found.append(Artifact(relative.replace("\\", "/"), path.stat().st_size, _stamp(path)))
    found.sort(key=lambda a: a.name)
    return found[:MAX_LISTED]


def list_projects(data_dir: str | Path) -> list[ProjectListing]:
    """Every production, newest first, each with its own file list.

    This is what makes a generation traceable from the browser: the flat
    artifacts listing shows single files, and a project is a directory those
    rules deliberately skip. A missing directory is an empty list.
    """

    directory = projects_dir(data_dir)
    if not directory.is_dir():
        return []
    found: list[ProjectListing] = []
    for path in directory.iterdir():
        if not path.is_dir() or path.is_symlink():
            continue
        if not SAFE_NAME.match(path.name):
            continue
        found.append(ProjectListing(path.name, _stamp(path), tuple(_project_files(path))))
    found.sort(key=lambda p: (p.modified, p.slug), reverse=True)
    return found[:MAX_LISTED]


def read_project_file(data_dir: str | Path, slug: str, name: str) -> tuple[bytes, str]:
    """One file out of one project, or ``ArtifactNotFound``.

    ``name`` is a project-relative path as the listing printed it. Every
    segment is validated against ``SAFE_NAME`` *before* joining - which
    rejects ``..``, absolute paths and empty segments outright - and the
    resolved result must still sit inside the project, catching the symlink
    whose own name is ordinary.
    """

    if not SAFE_NAME.match(slug or ""):
        raise ArtifactNotFound(slug)
    segments = (name or "").split("/")
    if not segments or not all(SAFE_NAME.match(segment) for segment in segments):
        raise ArtifactNotFound(name)
    root = (projects_dir(data_dir) / slug).resolve()
    if not root.is_dir() or projects_dir(data_dir).resolve() not in root.parents:
        raise ArtifactNotFound(slug)
    path = root.joinpath(*segments).resolve()
    if not path.is_file() or root not in path.parents:
        raise ArtifactNotFound(name)
    return path.read_bytes(), path.name


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
    "MEDIA_TYPES",
    "ProjectListing",
    "SAFE_NAME",
    "artifacts_dir",
    "list_artifacts",
    "list_projects",
    "media_type_for",
    "projects_dir",
    "read_artifact",
    "read_project_file",
]
