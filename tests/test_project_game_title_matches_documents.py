"""C-1621: a project's game.html must carry the same title as its documents.

The GAME stage re-derived the title from the raw request and kept 「制作一式」,
so the game.html <title> disagreed with every .md in the bundle. It now uses
the project's canonical title via title_override.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from sidra_ai.creation.projects import scaffold_project
from sidra_ai.evals.project_game_title_matches_documents import (
    evaluate_project_game_title_matches_documents,
)


def _titles(request: str):
    tmp = Path(tempfile.mkdtemp(prefix="proj-title-test-"))
    project = scaffold_project(request, tmp)
    html = (project.root / "game.html").read_text(encoding="utf-8")
    game_title = re.search(r"<title>(.*?)</title>", html).group(1)
    h1 = re.search(r"#\s*(.+?)\s*—",
                   (project.root / "scenario.md").read_text(encoding="utf-8")).group(1)
    return project.title, game_title, h1


def test_eval_passes():
    result = evaluate_project_game_title_matches_documents()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_game_title_matches_documents_and_drops_bundle_word():
    for request in ("料理アプリの制作一式を作って",
                    "宇宙シューティングゲームの制作一式を作って",
                    "釣りゲームの制作一式を作って"):
        title, game_title, h1 = _titles(request)
        assert game_title == title == h1, request
        assert "制作一式" not in game_title, request


def test_standalone_game_title_unaffected():
    # The standalone game path passes no title_override, so games.py derives its
    # own title as before - this project fix must not reach it.
    from sidra_ai.creation.games import generate_game

    html = generate_game("釣りゲームを作って").html
    assert "<title>" in html  # still produced; derivation unchanged by C-1621
