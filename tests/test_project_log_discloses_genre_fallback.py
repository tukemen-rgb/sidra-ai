"""C-1605: the production log must admit a default-template fallback.

The project summary said when game.html fell back to the default template
(C-1285), but a project is a saved/forwarded directory, so production-log.md now
carries the admission too - and stays quiet for a genuine game.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.project_job import build_project_generator
from sidra_ai.creation.projects import scaffold_project
from sidra_ai.evals.project_log_discloses_genre_fallback import (
    evaluate_project_log_discloses_genre_fallback,
)

_MARK = "既定テンプレートへのフォールバック"


def test_project_log_fallback_eval_passes():
    result = evaluate_project_log_discloses_genre_fallback()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def _log(request: str) -> str:
    tmp = Path(tempfile.mkdtemp())
    scaffold_project(request, tmp)
    root = next((tmp / "artifacts" / "projects").iterdir())
    return (root / "production-log.md").read_text(encoding="utf-8")


def test_non_game_request_log_discloses_fallback():
    assert _MARK in _log("料理アプリの制作一式を作って")
    assert "代わりに既定の" in _log("アクションゲームの制作一式を作って")


def test_genuine_game_log_has_no_caveat():
    assert _MARK not in _log("釣りゲームの制作一式を作って")


def test_summary_still_admits_fallback():
    gen = build_project_generator(tempfile.mkdtemp())
    msg = "料理アプリの制作一式を作って"
    summary = gen(msg, detect_creation_intent(msg)).summary
    assert "なお" in summary and "代わりに既定の" in summary
