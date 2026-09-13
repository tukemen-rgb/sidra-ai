"""偽の store は、本物のブラウザと同じ形で持つ (C-1749).

Nine probes in ``sidra_ai.creation`` fake ``localStorage``, and each has
to be seeded with what a previous visit left behind. They had drifted
into three different answers: strings raw and everything else JSON (six
of them), ``str()`` for everything (adapt), JSON for everything (round).

The platform's rule is one, and §31 already quotes the source: values are
strings, and ``setItem`` stringifies what it is handed. A seed therefore
has to be the string the page would read back.

* ``str({"a": 1})`` is Python's repr - no page can parse it.
* ``json.dumps("frost")`` is ``"frost"`` with quotes, and a page
  comparing a skin id against it matches nothing.

No judge was seeded wrongly - adapt is only handed numbers and round only
dicts - so this was a trap rather than a live defect. It had already cost
two wrong readings in one night (C-1747): a skin set in the store that
the page ignores reads exactly like a product that ignores skins.

Both directions: everyone uses the one seeder, and the seeder produces
what the page can read back.
"""

from __future__ import annotations

import inspect

import pytest

from sidra_ai.creation import (
    adapt,
    juice,
    marble,
    round as round_mod,
    share,
    skins,
    startscreen,
    together,
    tuning,
)
from sidra_ai.creation.probekit import seed_store

PROBERS = (adapt, juice, marble, round_mod, share, skins, startscreen, together, tuning)

#: value seeded, what the browser would hold, why it matters
CASES = (
    ("frost", "frost", "a skin id is read raw"),
    ("1", "1", "the briefing mark is read raw"),
    (3, "3", "a number reads the same either way"),
    ({"speed": 1.5}, '{"speed": 1.5}', "a dict is what the page wrote"),
    (True, "true", "a flag uses JS spelling, not Python's"),
    ([1, 2], "[1, 2]", "a list is JSON"),
)


@pytest.mark.parametrize("module", PROBERS, ids=[m.__name__.rsplit(".", 1)[-1] for m in PROBERS])
def test_every_prober_uses_the_one_seeder(module) -> None:
    source = inspect.getsource(module)
    assert "seed_store(" in source, module.__name__
    # ...and no hand-rolled remnant beside it.
    assert "(stored or {}).items()" not in source, module.__name__
    assert "seeded.items()" not in source, module.__name__


@pytest.mark.parametrize("value,want,why", CASES, ids=[c[2] for c in CASES])
def test_the_seeder_holds_what_the_browser_holds(value, want, why) -> None:
    """Without this, calling the shared function proves nothing."""

    assert seed_store({"k": value})["k"] == want, why


def test_a_python_repr_never_reaches_the_store() -> None:
    """``str()`` for everything was one of the three answers."""

    held = seed_store({"k": {"a": 1}})["k"]
    assert held == '{"a": 1}'
    assert "'" not in held, held


def test_a_raw_string_is_not_quoted() -> None:
    """JSON for everything was the other, and it cost two readings."""

    assert seed_store({"k": "frost"})["k"] == "frost"
    assert seed_store({"k": "frost"})["k"] != '"frost"'


def test_nothing_is_seeded_that_is_not_a_string() -> None:
    every = seed_store({str(i): v for i, (v, _w, _y) in enumerate(CASES)})
    assert all(isinstance(v, str) for v in every.values()), every


@pytest.mark.parametrize("module", PROBERS, ids=[m.__name__.rsplit(".", 1)[-1] for m in PROBERS])
def test_every_fake_setitem_stringifies(module) -> None:
    """A probe that stored objects would be a browser nobody has.

    Every ``setItem`` is checked, not merely that the spelling appears
    somewhere in the file: round.py alone has eight fakes, so one of them
    dropping the conversion is invisible to a module-wide search. The
    destruction battery walked through the version that searched.
    """

    import re as _re

    source = inspect.getsource(module)
    writes = _re.findall(r"setItem: \(k, v\) => \{[^}]*\}", source)
    for write in writes:
        assert "String(v)" in write, (module.__name__, write)
