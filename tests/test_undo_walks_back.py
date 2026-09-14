"""Undo must walk back through the history, not bounce off the last step.

C-1816. An undo writes a NEW version holding an OLD state and lands at the end
of the chain, so the next undo read its predecessor as "the state I was just
in" and copied that back. 「元に戻して」 three times ran the accent off, on, off;
``difficulty`` stayed ``hard`` for ever and the first change was unreachable.
Each reply said 「一つ前の版に戻しました」 - true of the files, false about the
history.

It stayed invisible because the undo summary named only difficulty, theme and
title, so an accent-only undo printed nothing and the oscillation read as the
same answer repeating. That is why the accent is named now, and why the eval
drives the sidecars rather than trusting the sentences.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.revise import _previous_version, save_meta  # noqa: E402


def _write(root: Path, name: str, *, difficulty: str, restored_from: str = "") -> Path:
    artifact = root / "artifacts" / f"{name}.html"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("<html></html>", encoding="utf-8")
    return save_meta(
        artifact,
        request="レースゲームを作って",
        template="racing",
        difficulty=difficulty,
        theme="",
        title="レース",
        panel={},
        restored_from=restored_from or None,
    )


def test_a_single_undo_still_reads_the_version_before_it(tmp_path: Path) -> None:
    """C-1513/C-1744's behaviour, unchanged."""

    _write(tmp_path, "game-racing-1", difficulty="normal")
    second = _write(tmp_path, "game-racing-2", difficulty="hard")

    found = _previous_version(tmp_path, second, {"request": "レースゲームを作って", "template": "racing"})
    assert found is not None and found[1]["difficulty"] == "normal"


def test_a_second_undo_walks_past_the_first(tmp_path: Path) -> None:
    """The defect: without `restored_from` this returned the state just left."""

    first = _write(tmp_path, "game-racing-1", difficulty="normal")
    second = _write(tmp_path, "game-racing-2", difficulty="hard")
    # the undo of `second`: a new version holding `first`'s state
    third = _write(tmp_path, "game-racing-3", difficulty="normal", restored_from=first.name)

    found = _previous_version(tmp_path, third, {"request": "レースゲームを作って", "template": "racing"})
    assert found is None, (
        "undoing back to the first version must report nothing earlier, not "
        f"hand back {found[0].name if found else None} - the state just left"
    )
    assert second.exists(), "no version may be deleted (§23)"


def test_a_chain_of_undos_does_not_spin(tmp_path: Path) -> None:
    """A restored_from cycle must stop rather than loop for ever."""

    a = _write(tmp_path, "game-racing-1", difficulty="normal")
    b = _write(tmp_path, "game-racing-2", difficulty="hard", restored_from="game-racing-3.meta.json")
    _write(tmp_path, "game-racing-3", difficulty="normal", restored_from=b.name)

    assert _previous_version(tmp_path, b, {"request": "レースゲームを作って", "template": "racing"}) is None
    assert a.exists()


def test_the_whole_conversation_walks_back_and_says_so() -> None:
    """Driven end to end, because the sidecars are where the truth was."""

    from sidra_ai.evals.undo_walks_back import evaluate_undo_walks_back

    result = evaluate_undo_walks_back()
    assert result.passed, result.failures
    assert result.checks_total == result.checks_passed + len(result.failures)
