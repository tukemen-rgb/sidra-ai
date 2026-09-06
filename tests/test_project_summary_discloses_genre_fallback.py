"""C-1285: the project summary admits a genre fall-back the game path admits.

The standalone game path says 「代わりに既定の…型で作りました」 when a genre it has no
template for lands on the default fishing page; the project bundling the same
game.html said nothing. The summary now carries the same admission, and stays
silent for a genre the tool actually builds.
"""

from __future__ import annotations

import tempfile

from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.router import build_default_router
from sidra_ai.evals.project_summary_discloses_genre_fallback import (
    evaluate_project_summary_discloses_genre_fallback,
)

_FALLBACK = "代わりに既定の"


def _summary(request: str) -> str:
    router = build_default_router(data_dir=tempfile.mkdtemp(prefix="proj-genre-t-"))
    return router.route(request, detect_creation_intent(request), []).summary


def test_project_summary_discloses_genre_fallback_eval_passes():
    result = evaluate_project_summary_discloses_genre_fallback()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_unrecognised_genre_project_discloses_default():
    s = _summary("アクションゲームの制作一式を作って")
    assert _FALLBACK in s and "タイミング釣り" in s
    assert "アクションゲーム" in s
    # the files are still listed - the project is still whole
    assert "game.html" in s and "scenario.md" in s


def test_unsupported_genre_project_names_the_genre():
    s = _summary("格闘ゲームの制作一式を作って")
    assert _FALLBACK in s and "対戦格闘" in s


def test_built_genre_project_draws_no_caveat():
    assert _FALLBACK not in _summary("釣りゲームの制作一式を作って")
    assert _FALLBACK not in _summary("シューティングの制作一式を作って")
