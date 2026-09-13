"""C-1790: the project design docs disclose a substituted genre, not just the log.

A project request for a genre SIDRA cannot build (「格闘」) writes
scenario/structure/features.md that describe the fishing default; each now
carries the genre_fallback_note (already used by production-log.md, the game
page and the chat summary), while a buildable genre adds no such note and the
docs stay the real spec.
"""

from __future__ import annotations

from sidra_ai.creation.projects import scaffold_project
from sidra_ai.evals.project_docs_disclose_genre_fallback import (
    evaluate_project_docs_disclose_genre_fallback,
)
from sidra_ai.evals.scratch import scratch_dir

_NOTE = "代わりに既定"


def test_project_docs_fallback_eval_passes():
    result = evaluate_project_docs_disclose_genre_fallback()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_each_design_doc_discloses_a_declined_genre():
    root = scaffold_project("格闘ゲームを企画から作って", scratch_dir()).root
    for name in ("scenario.md", "structure.md", "features.md"):
        assert _NOTE in (root / name).read_text(encoding="utf-8"), name


def test_a_buildable_genre_adds_no_note_to_the_docs():
    root = scaffold_project("パズルゲームを企画から作って", scratch_dir()).root
    assert _NOTE not in (root / "scenario.md").read_text(encoding="utf-8")


def test_the_disclosure_is_additive_not_a_replacement():
    root = scaffold_project("格闘ゲームを企画から作って", scratch_dir()).root
    assert "遊びの芯" in (root / "scenario.md").read_text(encoding="utf-8")
    assert "難易度パラメータ" in (root / "features.md").read_text(encoding="utf-8")
    # production-log.md kept its own disclosure (C-1605).
    assert _NOTE in (root / "production-log.md").read_text(encoding="utf-8")
