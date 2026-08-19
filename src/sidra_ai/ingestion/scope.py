"""What counts as a documentation file, defined once.

The ingestion pipeline reads a narrow slice of each repository: the README,
and documentation files under ``docs/``. Everything else - application code,
configuration, data files - is never fetched and never indexed.

This module exists because that rule was previously written down twice: once
in :meth:`GitHubReadOnlyClient.list_docs_paths`, which the product uses, and
once in ``scripts/measure_outcomes.py``, which decides what the product's
headline numbers are measured against. The two disagreed. The measurement
walked every text file in every checkout - ``.py``, ``.tsx``, ``.json``,
``.sh`` - and so scored retrieval over a corpus 5.5 times the size of the one
SIDRA actually holds, in which application source outranked the documents
carrying the answers.

A number measured against a corpus the product does not have is not a
pessimistic number, it is a number about a different system. Keeping the rule
in one place is what stops that from coming back.
"""

from __future__ import annotations

from typing import Iterable

#: File extensions the pipeline treats as documentation. Matches what
#: ``list_docs_paths`` accepts when walking the documentation roots.
DOCUMENTATION_SUFFIXES: tuple[str, ...] = (".md", ".markdown", ".txt", ".rst")

#: Directories the pipeline walks for documentation.
DOCUMENTATION_ROOTS: tuple[str, ...] = ("docs",)


def is_documentation_path(
    rel_path: str,
    *,
    roots: Iterable[str] = DOCUMENTATION_ROOTS,
    suffixes: Iterable[str] = DOCUMENTATION_SUFFIXES,
) -> bool:
    """Would the ingestion pipeline read this repository-relative path?

    Two things qualify: a README at the repository root, and a file with a
    documentation extension under one of the documentation roots. The README
    check is deliberately loose about extension because GitHub's readme
    endpoint picks the file rather than us naming it.

    Paths are compared case-insensitively and with backslashes normalised, so
    a checkout walked on any platform answers the same as the API does.
    """

    normalised = rel_path.replace("\\", "/").strip().lower()
    while normalised.startswith("./"):
        normalised = normalised[2:]
    if not normalised:
        return False
    # Reject traversal before anything else. ``lstrip("./")`` would strip a
    # character *set* and quietly turn "../secrets.md" into a root-level
    # document, so the check is on the segments themselves.
    segments = normalised.split("/")
    if any(segment in ("..", "") for segment in segments):
        return False
    if normalised.startswith("/"):
        return False

    # README at the root, whatever its extension: GitHub's readme endpoint
    # picks the file rather than us naming it. A "vendor/readme.md" is not
    # documentation of this repository and the pipeline never fetches it.
    if "/" not in normalised and normalised.startswith("readme"):
        return True

    if not normalised.endswith(tuple(suffixes)):
        return False

    # Documentation files at the repository root - SPEC.md, TODO.md and the
    # like. The root is listed but never descended into, so this is the top
    # level only and never "any .md anywhere".
    if "/" not in normalised:
        return True

    return any(
        normalised == root.lower() or normalised.startswith(f"{root.lower()}/")
        for root in roots
    )
