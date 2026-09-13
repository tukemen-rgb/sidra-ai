"""One interpreter, two spellings, is not two footings (C-1781).

C-1707 taught the judge to refuse a comparison between snapshots taken on
different interpreters, because the alternative was exit 2 - *revert this* -
for a difference that was entirely environmental. It refused one case too
many. The mark records ``venv`` as ``bool(os.environ.get("VIRTUAL_ENV"))``:
**whether** an activation script ran, not which interpreter answered. The same
binary is reachable both ways, and both spellings are what the documents tell
a reader to type - ``docs/LOCAL_RUNTIME.md`` writes the activation, this
script's own examples write the direct path - so taking a baseline one way and
measuring the other is an ordinary accident.

Measured on this tree 2026-09-13 before the fix: identical ``executable``,
identical ``python``, ``venv`` False -> True, and the real ``_report``
returned 3 **for an improvement and for a regression alike**. The printout
said "re-take the baseline with the interpreter you are about to compare
with", which cannot be followed when that interpreter is already the same one,
and re-taking it changes nothing unless the spelling happens to match.

Also measured rather than assumed: setting ``VIRTUAL_ENV`` changes neither
``sys.prefix`` nor site-packages (a venv interpreter reads its prefix from the
``pyvenv.cfg`` beside its own executable), so the path in ``executable``
already fixes the footing and the flag adds nothing to it. That is the reason
the flag may be dropped from the *comparison* - and the reason it must stay in
the *record*, which is a different thing and is checked below.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import product_metrics as pm  # noqa: E402
from product_metrics import OUTCOME, Metric  # noqa: E402

VENV_EXE = "/repo/.venv/bin/python"
#: One interpreter, called by its own path: the flag is off.
DIRECT = {"python": "3.11.15", "executable": VENV_EXE, "venv": False}
#: The same interpreter, reached through its activation script.
ACTIVATED = {"python": "3.11.15", "executable": VENV_EXE, "venv": True}
#: Genuinely somewhere else.
OTHER_EXE = {"python": "3.11.15", "executable": "/usr/bin/python3", "venv": True}
OTHER_VERSION = {"python": "3.12.4", "executable": VENV_EXE, "venv": False}


class _Collector:
    def __init__(self, value: float) -> None:
        self.metrics = [Metric("shipped", "shipped", value, kind=OUTCOME)]
        self.timings: list = []


def _before(mark=DIRECT, value: float = 1.0) -> dict:
    snap = {"shipped": {"value": value, "unit": "", "kind": OUTCOME, "detail": ""}}
    return {pm._ENV_KEY: dict(mark), **snap} if mark else snap


def _verdict(before: dict, value: float, mark: dict) -> tuple[int, str]:
    """Drive the real `_report`: the thing under test is the verdict."""

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


@pytest.mark.parametrize(
    "value, want", [(2.0, 0), (0.0, 2)], ids=["better", "worse"]
)
def test_the_flag_alone_does_not_refuse_the_comparison(
    value: float, want: int
) -> None:
    """Both directions. A fix that answered 0 to everything would pass the
    improvement case alone - and would be a judge that never stops anything."""

    code, said = _verdict(_before(), value, ACTIVATED)

    assert code != pm.CROSS_ENVIRONMENT, (
        "the same executable was called two ways, which is not two footings"
    )
    assert code == want
    assert "DIFFERENT FOOTING" not in said


@pytest.mark.parametrize(
    "mark, field",
    [(OTHER_EXE, "executable"), (OTHER_VERSION, "python")],
    ids=["another-executable", "another-version"],
)
def test_a_real_change_of_interpreter_still_stops(mark: dict, field: str) -> None:
    """C-1707's half, kept. Without it this file could be satisfied by a judge
    that refuses nothing at all."""

    code, said = _verdict(_before(), 0.0, mark)

    assert code == pm.CROSS_ENVIRONMENT
    assert "DIFFERENT FOOTING" in said
    assert field in said, "the reader has to be told which field disagreed"
    assert code != 2, "a footing difference is still not a revert order"


def test_the_flag_is_still_recorded_and_still_printed() -> None:
    """禁じ手 ①: what was wrong was the comparison, not the record. How a run
    was invoked is cheap to keep and worth reading later, so the flag stays in
    the mark and is still named beside a real difference."""

    assert "venv" in pm._env_mark()

    _, said = _verdict(
        _before(),
        0.0,
        {"python": "3.12.4", "executable": "/usr/bin/python3", "venv": True},
    )

    assert "venv" in said


def test_the_refusal_is_not_switched_off_wholesale() -> None:
    """禁じ手 ②: `env_mismatch` returning None for everything would reopen the
    hole C-1707 closed, and every test above about the flag would still pass."""

    assert pm.env_mismatch(_before(), {pm._ENV_KEY: OTHER_EXE}) is not None
    assert pm.env_mismatch(_before(), {pm._ENV_KEY: OTHER_VERSION}) is not None
    assert pm.env_mismatch(_before(), {pm._ENV_KEY: ACTIVATED}) is None


def test_an_unmarked_baseline_is_still_unknown_rather_than_wrong() -> None:
    """C-1707 (c), kept: refusing unmarked files would strand every
    measurement already written to disk."""

    code, said = _verdict(_before(mark=None), 2.0, ACTIVATED)

    assert code == 0
    assert "no record of what it was measured on" in said


def test_the_identity_of_an_interpreter_does_not_include_the_flag() -> None:
    assert "venv" not in pm._ENV_IDENTITY
    assert set(pm._ENV_IDENTITY) == {"python", "executable"}


def test_the_two_spellings_really_do_produce_the_same_executable() -> None:
    """The premise, driven in real subprocesses rather than asserted.

    If activation changed `sys.executable`, the flag would be redundant with
    the path and this whole item would be about nothing. The activation itself
    is simulated by exporting VIRTUAL_ENV, which is the only part of it the
    mark reads - there is no venv in every environment this suite runs in, and
    a test that needed one would be skipped exactly where it matters.
    """

    code = (
        "import importlib.util,sys,json;"
        "s=importlib.util.spec_from_file_location('pm','scripts/product_metrics.py');"
        "m=importlib.util.module_from_spec(s);sys.modules['pm']=m;"
        "s.loader.exec_module(m);print(json.dumps(m._env_mark()))"
    )
    root = Path(__file__).resolve().parents[1]

    def mark(venv: str | None) -> dict:
        # Set explicitly both ways, so this says the same thing whether or not
        # the suite itself was launched through an activation - otherwise the
        # two marks could come back identical and the check would pass by
        # measuring nothing.
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        if venv is not None:
            env["VIRTUAL_ENV"] = venv
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=root,
            env=env,
            timeout=120,
        )
        assert out.returncode == 0, out.stderr[-400:]
        return json.loads(out.stdout.strip().splitlines()[-1])

    off, on = mark(None), mark("/somewhere/.venv")

    assert (off["venv"], on["venv"]) == (False, True), "the flag has to differ"
    assert off["executable"] == on["executable"], (
        "if the flag moved the executable, the path would not be enough"
    )
    assert off["python"] == on["python"]
    assert pm.env_mismatch({pm._ENV_KEY: off}, {pm._ENV_KEY: on}) is None


def test_the_flag_changes_neither_prefix_nor_site_packages() -> None:
    """Why the path is sufficient: a venv interpreter reads its prefix from the
    `pyvenv.cfg` beside itself, not from the environment variable."""

    probe = "import sys,json;print(json.dumps([sys.prefix, sys.path]))"

    def paths(venv: str | None) -> list:
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        if venv is not None:
            env["VIRTUAL_ENV"] = venv
        out = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        assert out.returncode == 0, out.stderr[-400:]
        return json.loads(out.stdout.strip())

    assert paths(None) == paths("/somewhere/.venv")
