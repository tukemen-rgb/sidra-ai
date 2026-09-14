"""A baseline that could not measure must not be read as a baseline of zeroes.

``collect()`` does not stop when a section raises. It catches, writes
``<section>_probe`` into the snapshot as unmeasurable with the exception on
it, and runs the remaining sections - which is the right call, because one
broken probe should not cost the other nine. What follows from it is that
``--save`` can write a baseline that is missing a quarter of the board, with
the reason sitting in the file.

``compare``'s first loop walks the *new* snapshot and reads a key with no
counterpart in the baseline as newly measurable, which counts as movement.
Measured 2026-09-13 on a real 483-key snapshot: dropping ``measure_creation``
from the baseline side alone gives **245 movements, 0 regressions, exit 0** -
a full "done" for a commit that moved nothing. Dropping the same section from
the *new* side gives **247 regressions, exit 2**. The judge was strict about
the snapshot it took and trusted the one it was handed; this is the missing
half.

It is not hypothetical. This tree's 辛口クリエイター loop took a baseline in a
fresh container before the dependencies were installed and saved **13** of its
475 numbers. That was caught by eye. Uncaught, the next ``--compare`` would
have reported four hundred improvements and exited 0.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import product_metrics as pm  # noqa: E402
from product_metrics import CONTEXT, OUTCOME, Metric  # noqa: E402

MARK = {"python": "3.11.15", "executable": "/usr/bin/python3", "venv": False}


def _before(value: float | None = 1.0, **extra):
    return {
        pm._ENV_KEY: dict(MARK),
        "shipped": {"value": value, "unit": "", "kind": OUTCOME, "detail": ""},
        **extra,
    }


PROBE = {"value": None, "unit": "", "kind": CONTEXT, "detail": "KeyError: 'racing'"}


class _Collector:
    def __init__(self, value):
        self.metrics = [Metric("shipped", "shipped", value, kind=OUTCOME)]
        self.timings = []


def _verdict(before, value):
    """Drive the real `_report`, which is where the verdict is decided."""

    real = pm._snapshot
    pm._snapshot = lambda _c: {
        pm._ENV_KEY: dict(MARK),
        "shipped": {"value": value, "unit": "", "kind": OUTCOME, "detail": ""},
    }
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            return pm._report(before, _Collector(value)), out.getvalue()
    finally:
        pm._snapshot = real


def test_an_incomplete_baseline_is_refused_and_the_section_is_named() -> None:
    code, said = _verdict(_before(creation_probe=dict(PROBE)), 2.0)

    assert code != 0, "a baseline that could not measure is not evidence of progress"
    assert code != 2, "nothing about the tree got worse; exit 2 orders a revert"
    assert code == pm.CROSS_ENVIRONMENT
    assert "INCOMPLETE BASELINE" in said
    assert "creation" in said, "the reader has to be told which section to fix"
    assert "KeyError" in said, "the file already carries the reason; print it"


@pytest.mark.parametrize("value, want", [(0.0, 2), (2.0, 0)], ids=["worse", "better"])
def test_a_whole_baseline_still_rules_exactly_as_before(value, want) -> None:
    """Without this, a judge that refused every comparison would pass above."""

    assert _verdict(_before(), value)[0] == want


def test_an_ordinary_unmeasurable_number_is_not_a_broken_baseline() -> None:
    """The half that keeps the refusal from swallowing the feature next door.

    ``compare`` counts a previously unmeasurable outcome that gains a value as
    movement, on purpose and in writing: without it, work that no existing
    number can see would be permanently unfinishable. Only the section probes
    mean "a whole block died".
    """

    code, said = _verdict(_before(value=None), 1.0)

    assert code == 0, "unmeasurable -> a value is the designed way to finish work"
    assert "INCOMPLETE BASELINE" not in said


def test_a_probe_key_that_carries_a_number_is_not_a_confession() -> None:
    """Only the unmeasurable form is the collector admitting it failed."""

    answered = {"value": 1.0, "unit": "", "kind": CONTEXT, "detail": "fine"}
    assert pm.incomplete_baseline(_before(creation_probe=answered)) is None
    assert pm.incomplete_baseline(_before(creation_probe=dict(PROBE))) is not None


def test_every_failed_section_is_listed_not_just_the_first() -> None:
    said = pm.incomplete_baseline(
        _before(creation_probe=dict(PROBE), answers_probe=dict(PROBE))
    )

    assert said is not None
    assert "creation" in said and "answers" in said
