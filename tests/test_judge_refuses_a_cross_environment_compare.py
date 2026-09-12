"""Exit 2 means *revert this*. It must never mean *you changed interpreters*.

Measured 2026-09-12 by the 進捗監視 loop, on one tree, with not a byte of the
product changed: collecting once through a venv and once without it made
``--compare`` print ``REGRESSED: 400 number(s) moved the wrong way. Do not
merge.`` That is the strongest verdict this script has, and the printout gave
no hint that the difference was the environment. A loop reading it reverts
work that was never wrong (C-1707).

The snapshots could not disagree about their footing because they recorded
none: every top-level key in a snapshot was a metric. That flatness is also
why the mark is a reserved key both loops in ``compare`` skip - a mark read as
a metric would arrive from nowhere, and its absence in an older file would be
read as a number that vanished, which is C-1491's failure through another
door.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import product_metrics as pm  # noqa: E402
from product_metrics import OUTCOME, Metric  # noqa: E402

HERE = {"python": "3.11.15", "executable": "/usr/bin/python3", "venv": False}
THERE = {"python": "3.11.15", "executable": "/repo/.venv/bin/python", "venv": True}


def _before(mark=HERE, value=1.0):
    snap = {"shipped": {"value": value, "unit": "", "kind": OUTCOME, "detail": ""}}
    return {pm._ENV_KEY: dict(mark), **snap} if mark else snap


class _Collector:
    def __init__(self, value):
        self.metrics = [Metric("shipped", "shipped", value, kind=OUTCOME)]
        self.timings = []


def _verdict(before, value, mark):
    """Drive the real `_report`, which is where the verdict is decided."""
    real = pm._snapshot
    pm._snapshot = lambda _c: {
        pm._ENV_KEY: dict(mark),
        "shipped": {"value": value, "unit": "", "kind": OUTCOME, "detail": ""},
    }
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            return pm._report(before, _Collector(value)), out.getvalue()
    finally:
        pm._snapshot = real


def test_a_cross_environment_compare_is_not_a_revert_order() -> None:
    code, said = _verdict(_before(), 0.0, THERE)

    assert code != 2, "exit 2 tells a loop to revert work that was never wrong"
    assert code == pm.CROSS_ENVIRONMENT
    assert "DIFFERENT FOOTING" in said
    assert "revert" in said.lower(), "the way out has to be said, not implied"


@pytest.mark.parametrize(
    "value, want", [(0.0, 2), (2.0, 0)], ids=["worse", "better"]
)
def test_the_same_footing_still_rules_exactly_as_before(value: float, want: int) -> None:
    """The half that stops this being satisfied by refusing everything.

    A judge that answered "different footing" to every comparison would pass
    the test above and be useless.
    """

    assert _verdict(_before(), value, HERE)[0] == want


def test_a_snapshot_taken_before_this_existed_is_unknown_not_wrong() -> None:
    """Refusing unmarked files would strand every measurement already on disk."""

    code, said = _verdict(_before(mark=None), 2.0, HERE)

    assert code == 0
    assert "no record of what it was measured on" in said


def test_the_mark_is_never_read_as_a_number() -> None:
    """Both loops in `compare` walk snapshots key-by-key, so a mark that looked
    like a metric would appear as a number from nowhere - and vanish from any
    older file as a number lost."""

    marked, plain = _before(), _before(mark=None)
    metrics = {"shipped": Metric("shipped", "shipped", 1.0, kind=OUTCOME)}

    assert "__env__" not in pm._values(marked)
    assert pm.compare(marked, marked, metrics) == ([], [])
    # An older snapshot gaining a mark is not a new number...
    assert pm.compare(plain, marked, metrics) == ([], [])
    # ...and a marked one compared against an unmarked run has lost nothing.
    assert pm.compare(marked, plain, metrics) == ([], [])


def test_the_mark_does_not_change_between_runs() -> None:
    """C-1707's own precondition: a mark that varied would manufacture the
    very false difference this exists to prevent."""

    assert pm._env_mark() == pm._env_mark()
    assert pm.env_mismatch({pm._ENV_KEY: pm._env_mark()}, {pm._ENV_KEY: pm._env_mark()}) is None


def test_the_mark_records_whether_a_venv_is_active_not_which_one() -> None:
    """The value of VIRTUAL_ENV is a path and nothing here needs it."""

    mark = pm._env_mark()

    assert isinstance(mark["venv"], bool)
    assert all(isinstance(v, (str, bool)) for v in mark.values())


def test_the_real_snapshot_writes_the_mark() -> None:
    """The check above stubs `_snapshot`, so on its own it would pass a build
    that never recorded the footing at all - and then nothing downstream could
    ever detect a mismatch. Caught by destruction D1; this is the test that
    was missing."""

    snapshot = pm._snapshot(_Collector(1.0))

    assert pm._ENV_KEY in snapshot
    assert snapshot[pm._ENV_KEY] == pm._env_mark()
    assert "shipped" in snapshot, "the metrics must still be there beside it"
