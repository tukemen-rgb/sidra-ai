"""C-1723: the pre-push gate read four directories and called it "the tree".

``scripts/check_before_push.sh`` scanned ``docs/ src/ tests/ scripts/``.
``grep`` looks only where it is pointed, so a conflict marker anywhere else
got "OK to push". Measured 2026-09-12: 1976 files are tracked and 920 of them
are under those four, leaving 1056 - ``.claude/`` (1050), ``.github/`` (2)
and four files at the root - unexamined.

``.env.example`` is the one that hurts. Operators copy it into their own
``.env``, so a marker there ends up in a live configuration rather than in a
file someone is about to edit anyway.

The gate is the last thing standing between a rebase on shared ``main`` and a
push, so a hole in it is only visible when something goes wrong inside it.
These run the real script rather than reading it, because the defect was a
check that looked like it read the tree and did not.
"""

from __future__ import annotations

import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "check_before_push.sh"
MARKER = "<<<<<<< HEAD\nprobe\n>>>>>>> other\n"


def _run_gate() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(GATE)], capture_output=True, text=True, timeout=120
    )


@pytest.fixture
def probe(request):
    """An *untracked* file with a marker in it, removed however the test ends.

    Untracked on purpose: an interrupted test cannot leave a marker inside a
    file that is about to be committed.
    """

    path = REPO / request.param
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MARKER, encoding="utf-8")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def test_the_clean_tree_still_passes() -> None:
    """The direction a "refuse everything" fix would break.

    Also the guard on the two tests below: if this repository already had
    markers in it, their refusals would prove nothing.
    """

    done = _run_gate()

    assert done.returncode == 0, done.stdout[-400:]
    assert "OK to push" in done.stdout


@pytest.mark.parametrize(
    "probe",
    [
        # The five places the old scan never looked.
        ".github/.c1723_probe",
        ".claude/.c1723_probe",
        ".c1723_probe",
        # And the four it did, so this cannot pass by the scan having moved
        # rather than widened.
        "docs/.c1723_probe",
        "src/.c1723_probe",
    ],
    indirect=True,
)
def test_a_marker_anywhere_in_the_tree_is_refused(probe: pathlib.Path) -> None:
    done = _run_gate()

    assert done.returncode != 0, f"{probe} was not seen: {done.stdout[-300:]}"
    assert "REFUSED: conflict markers" in done.stdout
    assert str(probe.relative_to(REPO)) in done.stdout


@pytest.mark.parametrize(
    "half",
    [
        "<<<<<<< HEAD\n",
        ">>>>>>> other\n",
    ],
)
def test_each_half_of_a_marker_is_caught_on_its_own(half: str) -> None:
    """Found by breaking it: the probes above carry both lines, so dropping
    one of the two patterns left every test green while a real half-resolved
    conflict walked through. A rebase interrupted in the middle leaves
    exactly one of these behind."""

    path = REPO / ".github" / ".c1723_half_probe"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(half, encoding="utf-8")
    try:
        done = _run_gate()
    finally:
        path.unlink(missing_ok=True)

    assert done.returncode != 0, f"{half!r} was not seen: {done.stdout[-300:]}"
    assert "REFUSED: conflict markers" in done.stdout


def test_the_scan_asks_git_which_files_exist() -> None:
    """Not a spelling test: what is pinned is that the file set comes from
    git rather than from a written list of directories, which is the whole
    of this item. A future rewrite may use any command that does that."""

    source = GATE.read_text(encoding="utf-8")

    assert "git grep" in source
    assert "grep -rn" not in source, "the path-fixed scan is back"


def test_no_bare_equals_pattern() -> None:
    """A markdown setext underline is ``=======`` too, and docs/ has real
    ones (C-1709). Adding that pattern would make the gate refuse honest
    documents."""

    source = GATE.read_text(encoding="utf-8")

    assert "'^=======" not in source and '"^=======' not in source
    # And the thing that would have gone red: a real setext underline.
    underlines = list(REPO.glob("docs/*.md"))
    assert underlines, "no docs to check against"
