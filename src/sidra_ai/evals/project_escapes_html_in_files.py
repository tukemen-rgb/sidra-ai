"""Does the project scaffold neutralise HTML in its .md files?

C-1486, the projects twin of the document C-1483. Every other artifact that
becomes HTML - the deck, art, the GIF, the 3D preview - and the report (.md,
C-1483) escape fact text, titles and source labels. The project scaffold wrote
its Markdown files raw: the title (from the request) went into every stage
heading as ``# <script>… — 脚本``, and an evidence *source label* (the path of an
indexed Issue/PR body - EXTERNAL trust) went into the 「根拠にした索引」 list and
the production-log 生成履歴 line unescaped. Opened in a Markdown renderer that
permits inline HTML, that runs - a stored XSS via an artifact.

The scaffold now escapes the title and every source label in the .md it writes,
so tags display as the literal text the source held and never execute. The
stored ``.title`` stays raw (the chat summary is shown with textContent).

The checks read the .md files ``scaffold_project`` actually writes to disk.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)
_SCRIPT = "<script>alert(1)</script>"
_IMG = "<img src=x onerror=alert(2)>"


@dataclass(frozen=True)
class ProjectEscapeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _all_md(root: Path) -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(root.glob("*.md"))
    )


def evaluate_project_escapes_html_in_files() -> ProjectEscapeResult:
    from sidra_ai.creation.evidence import Fact
    from sidra_ai.creation.projects import scaffold_project

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A malicious title (from the request) and evidence whose *source labels*
    # carry HTML, as an indexed Issue/PR body would.
    evil_facts = [
        Fact("変更した。", f"docs/{_IMG}.md"),
        Fact("対応した。", f"issues/{_SCRIPT}"),
    ]
    d = tempfile.mkdtemp(prefix="proj-escape-")
    proj = scaffold_project(
        f"{_SCRIPT}のプロジェクトを作って", d, facts=evil_facts, now=_NOW
    )
    md = _all_md(proj.root)

    # 1-3: no raw executable tags survive anywhere in the .md files
    add("<script>alert(1)</script>" not in md, "raw <script> title survived in the .md files")
    add("<img src=x onerror" not in md, "raw <img onerror> source label survived")
    add(f"issues/{_SCRIPT}" not in md, "raw <script> source label survived in 根拠/生成履歴")

    # 4: the content is neutralised, not dropped - the escaped form is present
    add("&lt;script&gt;" in md, "the script text was dropped rather than escaped")

    # 5: the title heading is escaped (from the request)
    add("# &lt;script&gt;" in md and "# <script>" not in md,
        "the stage heading title was not escaped")

    # 6: the escaped source label is present (neutralised, not lost)
    add("&lt;img src=x onerror" in md, "the source label was dropped rather than escaped")

    # 7: the stored .title stays raw (the summary is shown with textContent)
    add(_SCRIPT in proj.title, "the stored title was altered (should stay raw)")

    # 8-10: a clean project is unaffected - real content survives, no spurious tags
    clean_dir = tempfile.mkdtemp(prefix="proj-clean-")
    clean = scaffold_project(
        "レースゲームのプロジェクトを作って",
        clean_dir,
        facts=[Fact("周回数は 3。", "docs/spec.md")],
        now=_NOW,
    )
    clean_md = _all_md(clean.root)
    add("レース" in clean_md, "a clean project lost its subject")
    add("docs/spec.md" in clean_md, "a clean source label was lost or mangled")
    add("&lt;" not in clean_md, "a clean project was disturbed by escaping")

    total = 10
    return ProjectEscapeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ProjectEscapeResult", "evaluate_project_escapes_html_in_files"]
