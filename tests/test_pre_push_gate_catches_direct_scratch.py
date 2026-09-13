"""C-1770's invariant is checked before a push, not only forty minutes after.

``test_evals_clean_up_their_scratch`` already forbids a judge from reaching
past ``evals/scratch.py``. It works, and it cannot arrive in time: it lives in
a suite that takes about forty minutes, so a judge that breaks the rule sits on
``main`` red until some other cycle trips over it.

Measured 2026-09-13, the day C-1770 landed: of the four judges added after it
that needed scratch space, **three called ``tempfile.mkdtemp`` directly** -
``citation_excerpt_follows_the_searched_query`` (C-1782),
``model3d_preview_discloses_mtl_color`` (C-1784) and
``art_page_discloses_color_not_applied`` (C-1786). Three separate loops spent
part of a cycle on the resulting red in one evening and two of them had not
written the judge.

So the same AST read runs from ``check_before_push.sh``, which every loop runs
in the seconds before pushing. This file checks the part that matters: that the
scan actually refuses, that the gate carries its verdict out, and that a check
which reads nothing does not pass for the wrong reason (C-1723's lesson).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_eval_scratch.py"
GATE = ROOT / "scripts" / "check_before_push.sh"
EVALS = ROOT / "src" / "sidra_ai" / "evals"

#: A judge that reaches past the helper, in the shape the real slips took:
#: a module-level `import tempfile` and one call.
OFFENDER = """\
import tempfile


def _service():
    return tempfile.mkdtemp()
"""

#: The same thing written across two lines, which a grep would miss.
OFFENDER_WRAPPED = """\
import tempfile


def _service():
    return tempfile.\\
mkdtemp()
"""


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, cwd=cwd, timeout=300
    )


@pytest.fixture
def planted(request) -> Path:
    """A throwaway judge in the real directory, removed however the test ends.

    Named with a leading underscore so no collector picks it up, and the
    cleanup is a finalizer rather than a `finally`, so a failing assertion
    still leaves the tree as it was.
    """

    path = EVALS / "_test_planted_offender.py"
    request.addfinalizer(lambda: path.unlink(missing_ok=True))
    return path


def test_the_tree_is_clean_right_now() -> None:
    """The control. Without it, every check below could pass on a tree that
    was already red for a reason nobody noticed."""

    done = _run(sys.executable, str(CHECK))

    assert done.returncode == 0, done.stdout + done.stderr
    assert "none reaches past" in done.stdout


@pytest.mark.parametrize(
    "source", [OFFENDER, OFFENDER_WRAPPED], ids=["one-line", "wrapped"]
)
def test_the_scan_refuses_a_judge_that_reaches_past_the_helper(
    planted: Path, source: str
) -> None:
    planted.write_text(source, encoding="utf-8")

    done = _run(sys.executable, str(CHECK))

    assert done.returncode == 1
    assert planted.name in done.stdout, "the reader has to be told which file"
    assert "scratch_dir" in done.stdout, "and what to do instead"


def test_the_gate_carries_the_refusal_out(planted: Path) -> None:
    """A check that prints a problem and lets the next command run is the
    whole of C-1660: the gate has to turn it into an exit code."""

    planted.write_text(OFFENDER, encoding="utf-8")

    done = _run("bash", str(GATE))

    assert done.returncode != 0
    assert planted.name in done.stdout
    assert "OK to push" not in done.stdout


def test_the_scan_finds_the_judges_from_wherever_it_is_run(tmp_path: Path) -> None:
    """It resolves the tree from its own location, not the caller's cwd.

    Written after the first version of the test below assumed the opposite:
    running it from a scratch directory still scanned the real judges, which is
    the behaviour a gate wants - a loop invoking it from a subdirectory must
    not get a green light for having read nothing.
    """

    done = _run(sys.executable, str(CHECK), cwd=tmp_path)

    assert done.returncode == 0
    assert "none reaches past" in done.stdout


def test_a_scan_that_reads_nothing_does_not_pass(tmp_path: Path) -> None:
    """C-1723's lesson: the gate once read four directories and called it the
    tree, and a check that reads nothing prints OK for the wrong reason. Here
    that state is reached the only way it can be - the script standing where
    no judges are, as it would after `evals/` were moved or renamed."""

    stranded = tmp_path / "scripts"
    stranded.mkdir()
    copy = stranded / CHECK.name
    copy.write_text(CHECK.read_text(encoding="utf-8"), encoding="utf-8")

    done = _run(sys.executable, str(copy))

    assert done.returncode == 2, done.stdout + done.stderr
    assert "read no judges" in done.stdout or "read nothing" in done.stdout

    # ...and the other half of "nothing": the directory is there but empty.
    (tmp_path / "src" / "sidra_ai" / "evals").mkdir(parents=True)
    empty = _run(sys.executable, str(copy))

    assert empty.returncode == 2
    assert "read nothing" in empty.stdout


def test_the_rule_is_not_written_down_twice() -> None:
    """The scan and the metric must not drift into two different rules. Both
    read with the AST, skip only the helper itself, and look for the same
    attribute call - so the check here is that neither has quietly become a
    grep."""

    text = CHECK.read_text(encoding="utf-8")

    assert "ast.walk" in text and "ast.parse" in text
    assert 'attr == "mkdtemp"' in text
    assert 'HELPER = "scratch.py"' in text


def test_a_mention_of_mkdtemp_in_a_string_is_not_a_call(planted: Path) -> None:
    """The scan reads calls, not text. A judge whose docstring explains the
    rule must not be reported as breaking it - otherwise the honest thing to
    do would be to stop writing the reason down."""

    planted.write_text(
        '"""This judge does not call tempfile.mkdtemp; it uses scratch_dir."""\n'
        "from sidra_ai.evals.scratch import scratch_dir\n\n\n"
        "def _service():\n    return scratch_dir()\n",
        encoding="utf-8",
    )

    done = _run(sys.executable, str(CHECK))

    assert done.returncode == 0, done.stdout + done.stderr
