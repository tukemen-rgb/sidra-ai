"""A snapshot says which tree it read, and an edited baseline says so (C-1789).

C-1707 taught a snapshot to record which interpreter answered. It left out the
other half: **which tree**. This collector measures the working tree, not a
commit, so a baseline taken while the change was already on disk records the
*fixed* numbers as "before" - and the comparison then reports NO MOVEMENT for
work that moved.

Measured 2026-09-13 by the loop it happened to, and written into that commit's
own message: ``ce1fd893`` took a background baseline that read the repair first
and recorded **4.0** where the true before was **0.0**. It was caught only
because the author happened to know the number should have been zero. The
apparatus said nothing.

The dangerous half of the fix is the half that must not happen. C-1781 spent a
whole cycle undoing a refusal that fired on a footing difference; the same
mistake on the tree axis would be worse, because every honest cycle has a dirty
tree and a baseline from an older commit. So this is a **note**, never a
verdict, and the tests below that pin the exit codes are the ones holding that
line - not the ones checking the wording.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import product_metrics as pm  # noqa: E402
from product_metrics import OUTCOME, Metric  # noqa: E402

NOTE = "BASELINE FROM AN EDITED TREE"

CLEAN = {
    "python": "3.11.15",
    "executable": "/usr/bin/python3",
    "venv": False,
    "commit": "a" * 40,
    "dirty": False,
}
#: What the run being compared always looks like: somebody changed something.
NOW = dict(CLEAN, dirty=True)


class _Collector:
    def __init__(self, value: float) -> None:
        self.metrics = [Metric("shipped", "shipped", value, kind=OUTCOME)]
        self.timings: list = []


def _snap(mark: dict | None, value: float = 1.0) -> dict:
    body = {"shipped": {"value": value, "unit": "", "kind": OUTCOME, "detail": ""}}
    return {pm._ENV_KEY: dict(mark), **body} if mark else body


def _verdict(before: dict, value: float, mark: dict) -> tuple[int, str]:
    real = pm._snapshot
    pm._snapshot = lambda _c: _snap(mark, value)
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            return pm._report(before, _Collector(value)), out.getvalue()
    finally:
        pm._snapshot = real


def test_the_mark_records_the_commit_and_whether_the_tree_was_edited() -> None:
    mark = pm._env_mark()

    assert "commit" in mark and "dirty" in mark
    assert isinstance(mark["commit"], (str, type(None)))
    assert isinstance(mark["dirty"], (bool, type(None)))


def test_the_real_snapshot_carries_it() -> None:
    """The checks below stub `_snapshot`, so on their own they would pass a
    build that never recorded the tree - and then nothing could ever notice."""

    snapshot = pm._snapshot(_Collector(1.0))

    assert pm._ENV_KEY in snapshot
    for field in ("commit", "dirty"):
        assert field in snapshot[pm._ENV_KEY]


def test_an_edited_baseline_is_said_out_loud() -> None:
    code, said = _verdict(_snap(dict(CLEAN, dirty=True)), 2.0, NOW)

    assert NOTE in said
    assert code == 0, "and it is still judged on the numbers"


@pytest.mark.parametrize(
    "mark, why",
    [
        (CLEAN, "a clean baseline"),
        (dict(CLEAN, commit=None, dirty=None), "a baseline git could not read"),
        (dict(CLEAN, commit="b" * 40), "a baseline from another commit"),
    ],
    ids=["clean", "unknown", "other-commit"],
)
def test_the_note_does_not_fire_on_an_ordinary_baseline(mark: dict, why: str) -> None:
    """A warning that fires every time is one nobody reads. Only the baseline
    is judged, and only when git actually said it was edited."""

    assert NOTE not in _verdict(_snap(mark), 2.0, NOW)[1], why


def test_the_run_being_compared_is_expected_to_be_dirty() -> None:
    """`--compare` means "I changed something, now measure": warning about the
    after side would fire on every honest comparison."""

    code, said = _verdict(_snap(CLEAN), 2.0, dict(CLEAN, dirty=True))

    assert NOTE not in said
    assert code == 0


@pytest.mark.parametrize(
    "value, want", [(2.0, 0), (0.0, 2)], ids=["better", "worse"]
)
def test_the_note_never_becomes_a_verdict(value: float, want: int) -> None:
    """The half that keeps C-1781's defect from being rebuilt on this axis.

    A refusal here would stop every real cycle, because every real cycle edits
    the tree before measuring.
    """

    code, said = _verdict(_snap(dict(CLEAN, dirty=True)), value, NOW)

    assert NOTE in said, "the note is still expected to appear"
    assert code != pm.CROSS_ENVIRONMENT, "an edited baseline is doubtful, not refusable"
    assert code == want


def test_a_baseline_with_no_tree_recorded_still_compares() -> None:
    """C-1707 (c)'s rule, kept: an older snapshot is unknown, not wrong."""

    older = {"python": "3.11.15", "executable": "/usr/bin/python3", "venv": False}

    assert _verdict(_snap(older), 2.0, NOW)[0] == 0


def test_the_footing_refusal_still_ignores_the_tree() -> None:
    """禁じ手 ①, at the helper: `env_mismatch` decides refusals, and neither a
    commit nor the dirty flag may reach it."""

    for changed in ({"commit": "c" * 40}, {"dirty": True}, {"commit": None}):
        assert pm.env_mismatch(
            {pm._ENV_KEY: CLEAN}, {pm._ENV_KEY: dict(CLEAN, **changed)}
        ) is None, f"{changed} must not refuse a comparison"
    # ...while a real change of interpreter still does.
    assert pm.env_mismatch(
        {pm._ENV_KEY: CLEAN},
        {pm._ENV_KEY: dict(CLEAN, executable="/usr/local/bin/python3")},
    ) is not None


def test_the_flags_are_read_from_a_real_repository(tmp_path: Path) -> None:
    """Driven in throwaway repositories rather than asserted, because "dirty"
    is the load-bearing half and a stub would prove nothing about git.

    Three trees: clean, edited, and not a repository at all.
    """

    def mark_of(script: Path) -> dict:
        """Load THAT copy of the script and ask it about its own tree.

        Pointing this at the real `product_metrics.py` is the mistake the
        first version of this test made: `_tree_mark` resolves the repository
        from its own file's location - correctly, so a run from a subdirectory
        still reads the right tree - so the copy inside the throwaway
        repository is the one that has to be imported.
        """

        probe = (
            "import importlib.util, sys, json;"
            f"s=importlib.util.spec_from_file_location('pm', {str(script)!r});"
            "m=importlib.util.module_from_spec(s);sys.modules['pm']=m;"
            "s.loader.exec_module(m);print(json.dumps(m._tree_mark()))"
        )
        done = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, cwd=script.parent, timeout=180,
        )
        assert done.returncode == 0, done.stderr[-400:]
        return json.loads(done.stdout.strip().splitlines()[-1])

    # `_tree_mark` reads the tree its own file sits in, so the repository has
    # to be built around a copy of the script.
    def repo(name: str) -> Path:
        root = tmp_path / name
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "product_metrics.py").write_text(
            Path(pm.__file__).read_text(encoding="utf-8"), encoding="utf-8"
        )
        # The real repository ignores it (.gitignore:16), and without the same
        # line here importing the script writes `scripts/__pycache__/` into the
        # tree it is about to measure - which made the first run of this test
        # report a freshly committed repository as edited. The measurement was
        # right; the repository really had an untracked file in it.
        (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        return root

    env_git = ["-c", "user.email=t@t", "-c", "user.name=t"]
    clean = repo("clean")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 [*env_git, "commit", "-qm", "first"]):
        subprocess.run(["git", *args], cwd=clean, check=True, timeout=120)

    script = clean / "scripts" / "product_metrics.py"
    got = mark_of(script)
    assert got["dirty"] is False, got
    assert isinstance(got["commit"], str) and len(got["commit"]) == 40
    assert got["commit"] != pm._tree_mark()["commit"], (
        "it read the throwaway repository, not the one the suite runs in"
    )

    (clean / "scripts" / "extra.txt").write_text("edited", encoding="utf-8")
    edited = mark_of(script)
    assert edited["dirty"] is True, "an untracked file is an edited tree"
    assert edited["commit"] == got["commit"]

    # Not a repository: unknown, and it must not raise or refuse.
    unknown = mark_of(repo("outside") / "scripts" / "product_metrics.py")
    assert unknown == {"commit": None, "dirty": None}, unknown


def test_no_git_at_all_is_unknown_rather_than_a_crash(tmp_path: Path) -> None:
    """禁じ手 ②, the arm the test above does not reach.

    Outside a repository git answers cleanly with a non-zero exit, so that
    path never touches the OSError branch. The branch is for git being
    *absent* - a machine without it, or a stripped PATH - and a destruction
    probe found the test suite blind to exactly that: making the failure
    re-raise broke nothing. Driven with an empty PATH, which is the only way
    to reach it.
    """

    script = tmp_path / "scripts" / "product_metrics.py"
    script.parent.mkdir(parents=True)
    script.write_text(Path(pm.__file__).read_text(encoding="utf-8"), encoding="utf-8")

    probe = (
        "import importlib.util, sys, json;"
        f"s=importlib.util.spec_from_file_location('pm', {str(script)!r});"
        "m=importlib.util.module_from_spec(s);sys.modules['pm']=m;"
        "s.loader.exec_module(m);print(json.dumps(m._tree_mark()))"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, cwd=tmp_path, timeout=180,
        env={"PATH": "/nonexistent", "PYTHONDONTWRITEBYTECODE": "1"},
    )

    assert done.returncode == 0, (
        "a measurement must stay takeable where git is not installed: "
        + done.stderr[-400:]
    )
    assert json.loads(done.stdout.strip().splitlines()[-1]) == {
        "commit": None, "dirty": None,
    }


def test_the_note_survives_a_run_that_cannot_read_git() -> None:
    """禁じ手 ②: nothing here may make a measurement impossible to take."""

    unknown = dict(CLEAN, commit=None, dirty=None)

    code, said = _verdict(_snap(unknown), 2.0, unknown)

    assert code == 0
    assert NOTE not in said
