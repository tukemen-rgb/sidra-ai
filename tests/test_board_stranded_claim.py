"""C-1728: a claim line left behind when its number was reassigned.

When a claim is renumbered the completion is written on a new line under
the new number and the original 「[~]」 stays. Two were live on 2026-09-12
(C-1694, C-1699) and neither existing invariant sees them: the number is
unique and the item is unfinished, which is what a real claim looks like.

The tell is that the metric the claim promises to 新設 has already been
新設 on a finished line.

That alone is not enough, and the measurement is why. Replayed over the
158 board versions between 2026-09-11 06:00 and 2026-09-12 16:00, the bare
rule also fires on four LIVE claims - C-1660, C-1696, C-1701, C-1704 -
each in exactly one version: the gap between writing a completion line and
flipping one's own box. Those states reached pushed versions, so the bare
rule would have blocked every loop four times in two days, on somebody
else's half-finished edit.

Nothing structural separates them: claim-to-completion distance is 1-8
lines for the strandings and 1-3 for the in-flight ones. What separates
them is that a stranding *persists*. So the previous board is an input and
a claim has to be stranded in both; replayed again, the strandings still
fire and the four live claims fire zero times.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_backlog_board.py"

_spec = importlib.util.spec_from_file_location("check_backlog_board", SCRIPT)
board_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(board_check)

HEAD = "### A. 試験用\n"
GHOST = (
    "- [~] 確保 2026-09-12 18:00 UTC 辛口クリエイター **C-9001: 試験用。**"
    "（`creation_probe_metric_xyz` 新設 unmeasurable→1 を約束する）"
)
DONE = (
    "- [x] 完了 2026-09-12 18:05 UTC 辛口クリエイター（`creation_probe_metric_xyz` "
    "**新設 unmeasurable→1**、判定器 exit 0）**C-9002: 試験用の完了。**"
)
MENTIONS = (
    "- [~] 確保 2026-09-12 18:00 UTC 辛口クリエイター **C-9003: 先行の "
    "`creation_probe_metric_xyz` を本文で挙げるだけ。**"
)

#: The shape that actually tests the immediacy rule: this claim *mentions*
#: the finished metric as context and *promises* a different one. A rule
#: that only required 新設 somewhere on the line would read the mention as
#: the promise and call a live claim stranded.
MENTIONS_ONE_PROMISES_ANOTHER = (
    "- [~] 確保 2026-09-12 18:00 UTC 辛口クリエイター **C-9004: "
    "`creation_probe_metric_xyz` の続きとして、`creation_probe_metric_abc` "
    "新設 unmeasurable→1 を約束する。**"
)

STRANDED = HEAD + GHOST + "\n" + DONE + "\n"
CONTEXT_THEN_PROMISE = HEAD + MENTIONS_ONE_PROMISES_ANOTHER + "\n" + DONE + "\n"
ANNOTATED = HEAD + GHOST + "\n      **注（この行は取り残しです）**\n" + DONE + "\n"
LIVE = HEAD + MENTIONS + "\n" + DONE + "\n"


def test_a_stranded_claim_standing_in_both_boards_is_reported() -> None:
    problems = board_check.check(STRANDED, STRANDED)

    assert problems, "the stranded claim was not seen"
    assert "C-9001" in problems[0]
    assert "creation_probe_metric_xyz" in problems[0]


def test_a_claim_stranded_in_only_this_board_is_left_alone() -> None:
    """The measured false positive: a completion written just before its
    own box was flipped. Four of those reached pushed board versions."""

    assert board_check.check(STRANDED, HEAD) == []


def test_naming_a_metric_as_context_is_not_promising_it() -> None:
    assert board_check.check(LIVE, LIVE) == []


def test_a_claim_that_cites_one_metric_and_promises_another_is_live() -> None:
    """Found by breaking it: the first version of this file only tested a
    mention with no 新設 on the line at all, so loosening the rule to
    「新設 anywhere on the line」 broke nothing and the destructive check
    passed for the wrong reason. Here the word is present - on a different
    metric - which is what the immediacy rule is actually for."""

    assert board_check.check(CONTEXT_THEN_PROMISE, CONTEXT_THEN_PROMISE) == []


def test_an_acknowledged_stranding_is_left_alone() -> None:
    """The escape that let this ship without turning the gate red: the two
    live strandings were already annotated, in those words, by the loop
    that found them."""

    assert board_check.check(ANNOTATED, ANNOTATED) == []


def test_without_a_previous_board_the_invariant_is_skipped() -> None:
    """Every existing caller passes one board and must keep its behaviour."""

    assert board_check.check(STRANDED) == []


def test_the_real_board_is_clean() -> None:
    """Both of today's strandings carry their note, so the gate is green."""

    board = (REPO / "docs" / "BACKLOG.md").read_text(encoding="utf-8")

    assert board_check.check(board, board) == []


# ------------------------------------------------------- through the CLI


def _repo_with(first: str, second: str, tmp_path: pathlib.Path) -> pathlib.Path:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path),
    }
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    for n, text in enumerate((first, second)):
        # The two versions must differ, or git records one commit and there
        # is no previous version - the state the invariant skips.
        (docs / "BACKLOG.md").write_text(text + f"\n<!-- {n} -->\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=tmp_path, env=env, check=True)
    return docs / "BACKLOG.md"


def _run_cli(board: pathlib.Path, home: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python", str(SCRIPT), str(board)],
        capture_output=True, text=True, timeout=120,
        env={"PATH": os.environ.get("PATH", ""), "HOME": str(home)},
    )


def test_the_cli_refuses_a_stranded_claim(tmp_path: pathlib.Path) -> None:
    board = _repo_with(STRANDED, STRANDED, tmp_path)

    done = _run_cli(board, tmp_path)

    assert done.returncode == 1, done.stdout
    assert "C-9001" in done.stdout


@pytest.mark.parametrize(
    "first,second,why",
    [
        (LIVE, LIVE, "a live claim naming a metric as context"),
        (CONTEXT_THEN_PROMISE, CONTEXT_THEN_PROMISE,
         "a live claim citing one metric and promising another"),
        (ANNOTATED, ANNOTATED, "a stranding somebody has already noted"),
        (HEAD, STRANDED, "a stranding that exists in this board only"),
    ],
)
def test_the_cli_passes_the_other_direction(
    first: str, second: str, why: str, tmp_path: pathlib.Path
) -> None:
    board = _repo_with(first, second, tmp_path)

    done = _run_cli(board, tmp_path)

    assert done.returncode == 0, f"{why}: {done.stdout}"


def test_the_previous_board_is_the_previous_version_of_the_file(
    tmp_path: pathlib.Path,
) -> None:
    """Found by breaking it: taking HEAD~1 blindly returned the same text
    whenever the last commits did not touch the board - which is most of
    them - and the invariant was skipped in silence."""

    board = _repo_with(STRANDED, STRANDED, tmp_path)
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path),
    }
    # Three commits that do not touch the board at all.
    for n in range(3):
        (tmp_path / f"other{n}.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "y"], cwd=tmp_path, env=env, check=True)

    done = _run_cli(board, tmp_path)

    assert done.returncode == 1, f"the invariant went quiet: {done.stdout}"
