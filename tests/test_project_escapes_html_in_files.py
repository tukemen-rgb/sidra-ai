"""C-1486: the project scaffold neutralises HTML in its .md files.

The projects twin of the document C-1483. The scaffold wrote the request into
every stage heading raw (``# <script>… — 脚本``) and an evidence source label
(an indexed Issue/PR path, EXTERNAL trust) into the 根拠 list and the
production-log line raw - a stored XSS when opened in a Markdown renderer that
permits inline HTML.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.projects import scaffold_project
from sidra_ai.evals.project_escapes_html_in_files import (
    evaluate_project_escapes_html_in_files,
)

_NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)
_SCRIPT = "<script>alert(1)</script>"
_IMG = "<img src=x onerror=alert(2)>"


def _all_md(root: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(root.glob("*.md")))


def test_project_escape_eval_passes():
    result = evaluate_project_escapes_html_in_files()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_title_and_source_labels_are_escaped_in_every_md():
    proj = scaffold_project(
        f"{_SCRIPT}のプロジェクトを作って",
        tempfile.mkdtemp(),
        facts=[Fact("変更した。", f"docs/{_IMG}.md"), Fact("対応。", f"issues/{_SCRIPT}")],
        now=_NOW,
    )
    md = _all_md(proj.root)
    assert "<script>alert(1)</script>" not in md
    assert "<img src=x onerror" not in md
    assert "&lt;script&gt;" in md
    assert "&lt;img src=x onerror" in md
    # the stored title stays raw (the chat summary is shown with textContent)
    assert _SCRIPT in proj.title


def test_clean_project_is_unaffected():
    clean = scaffold_project(
        "レースゲームのプロジェクトを作って",
        tempfile.mkdtemp(),
        facts=[Fact("周回数は 3。", "docs/spec.md")],
        now=_NOW,
    )
    md = _all_md(clean.root)
    assert "レース" in md
    assert "docs/spec.md" in md
    assert "&lt;" not in md
