"""A synthesised keydown carries two halves, and they are not the same.

C-1623 found a probe pressing a key no page was listening for: it put the
key into ``code`` as well, so the space bar arrived as ``code: ' '`` - a
code no browser produces - and every template that gates on
``e.code==='Space'`` sat untouched through five thousand frames of
"mashing". C-1626 found the same mistake in eight more places, and in one
of them it had turned into a written conclusion: ``adventure_losable``
recorded that "the sword turned out to be a red herring" from a drive whose
sword was never drawn.

The mistake is invisible from a passing run - the page simply does nothing -
so it is caught here, at the source, across every module that builds one of
these events rather than only the one where it was first found.
"""

from __future__ import annotations

import pathlib
import re

import pytest

#: ``code: k`` / ``code: key`` - the key put where the code belongs - and
#: ``key: code``, the same error the other way round.
_WRONG = re.compile(r"""(code:\s*(?:k|key)\s*[,}])|(key:\s*code\s*[,}])""")

_ROOTS = ("src", "tests", "scripts")


def _sources() -> list[pathlib.Path]:
    here = pathlib.Path(__file__).resolve().parent.parent
    return sorted(
        path
        for root in _ROOTS
        for path in (here / root).rglob("*.py")
        if "__pycache__" not in path.parts
        # This file quotes the mistake on purpose, to prove the scan sees it.
        and path.name != pathlib.Path(__file__).name
    )


def test_the_repository_has_sources_to_scan() -> None:
    """A guard that reads nothing passes for the wrong reason."""

    found = _sources()
    assert len(found) > 100, len(found)


@pytest.mark.parametrize("path", _sources(), ids=lambda p: p.name)
def test_no_synthesised_key_event_puts_a_key_where_the_code_goes(path) -> None:
    text = path.read_text(encoding="utf-8")
    bad = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(text.splitlines(), 1)
        if _WRONG.search(line)
    ]

    assert bad == [], "\n".join(bad)


def test_the_scan_would_catch_the_mistake_it_exists_for() -> None:
    """Both shapes, and the correct one left alone."""

    assert _WRONG.search("fn({ key: key, code: key, preventDefault(){} })")
    assert _WRONG.search("const e = { key: k, code: k, preventDefault(){} };")
    assert _WRONG.search("{ key: code, code: code, clientX: 0 }")
    assert not _WRONG.search(
        "{ key: k === 'Space' ? ' ' : k, code: k === ' ' ? 'Space' : k, }"
    )
    assert not _WRONG.search("{ key: ' ', code: 'Space' }")
