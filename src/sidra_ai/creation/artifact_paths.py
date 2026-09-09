"""One rule for naming a freshly saved artifact so a save never overwrites.

The generators stamp filenames to the second (``...-20260909T021530Z``). Two
artifacts of the same kind written inside one second - two chat requests
finishing together, a revision following its original - reduce to the same
name, and an unconditional ``write_text``/``write_bytes`` would silently
overwrite the first. ``save_game`` already guards this with a serial suffix;
this is that guard, factored out so every flat generator shares it.
"""

from __future__ import annotations

from pathlib import Path


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """A path ``<stem><suffix>`` in ``directory`` that does not yet exist.

    On collision the stem gains ``-2``, ``-3`` … until a free name is found,
    exactly as ``save_game`` does. Overwriting the earlier file would make
    "the old version is still there" a lie, so every save stays a new file.
    """

    path = directory / f"{stem}{suffix}"
    serial = 1
    while path.exists():
        serial += 1
        path = directory / f"{stem}-{serial}{suffix}"
    return path
