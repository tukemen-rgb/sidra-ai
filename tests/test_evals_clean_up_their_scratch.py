"""C-1770: a judge removes the scratch it made.

Ninety-three call sites across eighty eval modules reached for
``tempfile.mkdtemp()`` and none removed what they made. One collector run
left 159 directories behind; a week of five loops measuring all day left
``/tmp`` holding 30G, ``qa-honesty-*`` alone at 10,697 directories dating
back to 09-05, until the session's disk ran out and ``git pull`` failed
with ENOSPC.

It is a measurement problem, not a tidiness one. A full disk kills the
collector partway and ``--compare`` then reports every metric it never
reached as REGRESSED and LOST - which happened, and was read as a product
failure before the real cause was found.

Cleanup is at interpreter exit, so "did it clean up" can only be asked
from outside: these drive a subprocess with a ``TMPDIR`` of its own.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.evals.scratch import (  # noqa: E402
    scratch_dir,
    scratch_made,
    sweep_scratch,
)

EVALS = pathlib.Path(__file__).resolve().parents[1] / "src" / "sidra_ai" / "evals"

DRIVE = """
import sys, os, json
sys.path.insert(0, "src")
from sidra_ai.evals.qa_honesty import evaluate_qa_honesty
from sidra_ai.evals.creation_unbuildable_declined import (
    evaluate_creation_unbuildable_declined,
)
a = evaluate_qa_honesty()
b = evaluate_creation_unbuildable_declined()
print("SCRATCH " + json.dumps({
    "during": len(os.listdir(os.environ["TMPDIR"])),
    "answered": [a is not None, b is not None]}))
"""


@pytest.fixture(scope="module")
def driven() -> dict:
    home = tempfile.mkdtemp(prefix="c1770-test-")
    try:
        out = subprocess.run(
            [sys.executable, "-c", DRIVE],
            cwd=str(EVALS.parents[2]),
            env=dict(os.environ, TMPDIR=home),
            capture_output=True, text=True, timeout=900,
        )
        assert out.returncode == 0, out.stderr[-500:]
        said = [l for l in out.stdout.splitlines() if l.startswith("SCRATCH ")]
        assert said, out.stdout[-500:]
        seen = json.loads(said[-1][len("SCRATCH "):])
        seen["left"] = sorted(p.name for p in pathlib.Path(home).iterdir())
        return seen
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_nothing_outlives_the_process(driven: dict) -> None:
    assert driven["left"] == [], driven["left"]


def test_the_judges_really_used_scratch(driven: dict) -> None:
    """Otherwise leaving nothing behind proves nothing."""

    assert driven["during"] > 0


def test_the_judges_still_answered(driven: dict) -> None:
    """And otherwise a judge that does nothing scores full marks."""

    assert all(driven["answered"])


def test_no_judge_reaches_past_the_shared_helper() -> None:
    """Read with the AST, so a call spelled across two lines still counts."""

    direct = []
    for path in sorted(EVALS.glob("*.py")):
        if path.name == "scratch.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "mkdtemp"
            ):
                direct.append(path.name)
                break

    assert direct == [], direct


# ------------------------------------------------------------ the helper


def test_the_sweep_removes_what_it_handed_out() -> None:
    made = scratch_dir(prefix="c1770-unit-")
    assert pathlib.Path(made).is_dir()
    assert made in scratch_made()

    swept = sweep_scratch()

    assert swept >= 1
    assert not pathlib.Path(made).exists()
    assert scratch_made() == ()


def test_the_sweep_survives_a_directory_somebody_else_removed() -> None:
    """A judge that has already reported must not be turned into a failure
    by scratch that is gone - and this runs during interpreter shutdown,
    where raising is printed and ignored anyway."""

    made = scratch_dir(prefix="c1770-gone-")
    shutil.rmtree(made)

    assert sweep_scratch() >= 1
    assert scratch_made() == ()
