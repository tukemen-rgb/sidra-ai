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

# --- C-1651: the scan detects a recurrence; the helper prevents one ----
#
# The scan above works - it caught the same slip twice more in one session
# (C-1645's scene probe, C-1650's ear/eye probe), both of which "worked"
# by luck because adventure listens on ``e.key`` and racing's probe only
# ever pressed ``r``. What it cannot do is stop the next copy being typed,
# because every probe hand-writes the same branch.
#
# ``probekeys`` owns the branch now. These tests hold two things: the
# helper does the pairing correctly when actually run, and the number of
# places still writing it by hand may fall but never rise - so a new probe
# cannot add one.

#: A key paired with ``'Space'`` by hand: either the literal code, or the
#: ``k === ' ' ? 'Space'`` branch under any variable name.
_BY_HAND = re.compile(
    r"""code\s*:\s*(?:'Space'|"Space"|[A-Za-z_$][\w$]*\s*===?\s*' '\s*\?\s*'Space')"""
)

#: Files that own the pattern rather than copy it.
_OWNS_IT = ("probekeys.py", pathlib.Path(__file__).name)

#: Measured 2026-09-11 (C-1651), after migrating the two probes the
#: recurrence happened in. The bulk migration is C-1654; until then this
#: number is the ratchet. **It may be lowered, never raised** - a new
#: probe that hand-writes the branch has to fail here rather than wait to
#: be found by the scan above after it has already gone wrong once.
_HAND_ROLLED_SITES = 127
_HAND_ROLLED_FILES = 32


def _hand_rolled() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _sources():
        if path.name in _OWNS_IT:
            continue
        found = sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                    if _BY_HAND.search(line))
        if found:
            counts[str(path)] = found
    return counts


def test_the_ratchet_only_turns_one_way() -> None:
    counts = _hand_rolled()
    sites, files = sum(counts.values()), len(counts)

    assert sites <= _HAND_ROLLED_SITES, (
        f"a new probe wrote the key/code branch by hand ({sites} sites, was "
        f"{_HAND_ROLLED_SITES}). Embed probekeys.KEY_EVENT_SLOT and call "
        f"probeKey(k) instead:\n" + "\n".join(f"  {k}: {v}" for k, v in counts.items())
    )
    assert files <= _HAND_ROLLED_FILES, (sites, files)


def test_the_ratchet_is_not_already_stale() -> None:
    """A number left far above the truth would let several new copies in
    before anybody noticed."""

    sites = sum(_hand_rolled().values())

    assert sites >= _HAND_ROLLED_SITES - 5, (
        f"{_HAND_ROLLED_SITES - sites} sites were migrated without lowering "
        f"the ratchet to {sites}"
    )


def test_the_two_probes_the_slip_recurred_in_use_the_helper() -> None:
    from sidra_ai.creation.adventure import SCENE_ORDER_PROBE
    from sidra_ai.creation.probekeys import KEY_EVENT_SLOT
    from sidra_ai.creation.racing import EAR_EYE_PROBE

    for name, source in (("scene order", SCENE_ORDER_PROBE), ("ear/eye", EAR_EYE_PROBE)):
        assert KEY_EVENT_SLOT in source, name
        assert not _BY_HAND.search(source), name


def test_the_helper_pairs_the_halves_the_way_a_browser_does() -> None:
    """Run it, rather than read it: this is the one branch the repository
    has got wrong four times."""

    import json
    import subprocess

    from sidra_ai.creation.probekeys import KEY_EVENT_JS

    source = KEY_EVENT_JS + """
const seen = {};
for (const k of [' ', 'Space', 'r', 'ArrowLeft']) {
  const e = probeKey(k);
  seen[k] = [e.key, e.code, typeof e.preventDefault, typeof e.stopImmediatePropagation];
}
console.log(JSON.stringify(seen));
"""
    run = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr[:300]
    seen = json.loads(run.stdout.strip().splitlines()[-1])

    # Both spellings of the space bar give what a browser sends, so a probe
    # cannot get the halves the wrong way round by writing the argument the
    # other way - which is how C-1650 went wrong.
    assert seen[" "][:2] == [" ", "Space"]
    assert seen["Space"][:2] == [" ", "Space"]
    # ...and an ordinary key is untouched.
    assert seen["r"][:2] == ["r", "r"]
    assert seen["ArrowLeft"][:2] == ["ArrowLeft", "ArrowLeft"]
    for entry in seen.values():
        assert entry[2:] == ["function", "function"], entry


def test_the_helper_declares_what_it_introduces() -> None:
    """The same contract the animation preamble keeps: a probe that already
    had a ``probeKey`` would be shadowed silently otherwise."""

    from sidra_ai.creation.probekeys import KEY_EVENT_JS, KEY_EVENT_NAMES

    declared = {f"function {name}(" for name in KEY_EVENT_NAMES}
    defined = set(re.findall(r"function\s+(\w+)\s*\(", KEY_EVENT_JS))

    assert defined == set(KEY_EVENT_NAMES), (defined, KEY_EVENT_NAMES)
    for text in declared:
        assert text in KEY_EVENT_JS
