"""Does the report neutralise HTML that rode in on a fact or the request?

C-1483. Every other artifact that becomes HTML - the deck, art, the game, the 3D
preview - runs fact text through ``plain_text`` and then ``escape()``. The report
(.md) ran only ``plain_text``, which does not touch HTML, so a fact carrying
``<script>alert(1)</script>`` (allowed into the index by the gate - it is neither
a secret nor a prompt injection) was written into the document raw, as was a
``<script>`` in the request that became the title. Opened in a Markdown renderer
that permits inline HTML, that runs - a stored XSS via an artifact, seeded by an
EXTERNAL-trust Issue or PR body.

The document now escapes fact text, source labels and the title in the markdown
it emits, so the tags display as the literal text the source held and never
execute. The stored ``.title`` stays raw (the summary is shown with textContent).

The checks read the markdown ``generate_document`` produces.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sidra_ai.creation.documents import generate_document, validate_document
from sidra_ai.creation.evidence import Fact

_NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)
_SCRIPT = "<script>alert(1)</script>"
_IMG = "<img src=x onerror=alert(2)>"


def _md(request, facts):
    return generate_document(request, facts=facts, now=_NOW).markdown


@dataclass(frozen=True)
class DocumentEscapeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_escapes_html_in_evidence() -> DocumentEscapeResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    facts = [
        Fact(f"課題: {_SCRIPT} が残る。", "docs/a.md"),
        Fact(f"画像 {_IMG} を確認。", "docs/b.md"),
        Fact("根拠は 42 件。</section>後続テキスト", "docs/c.md"),
    ]
    md = _md(f"{_SCRIPT}のセキュリティレポートを作って", facts)

    # 1-3: no raw executable tags survive anywhere in the document
    add("<script>" not in md, "raw <script> survived in the document")
    add("<img src=x onerror" not in md, "raw <img onerror> survived in the document")
    add("</section>" not in md, "raw </section> breakout survived in the document")

    # 4: the content is neutralised, not dropped - the escaped form is present
    add("&lt;script&gt;" in md, "the script text was dropped rather than escaped")

    # 5-6: the title (from the request) is escaped in the heading and the 概要
    add("# <script>" not in md, "raw <script> survived in the title heading")
    add("「<script>" not in md, "raw <script> survived in the 概要 preamble")

    # 7: legitimate fact content is preserved (only the tags are neutralised)
    add("課題:" in md and "が残る" in md, "legitimate fact text was lost")
    add("42 件" in md, "a sourced number was lost from the body")

    # 8: a source label carrying HTML is escaped too
    evil_src = _md("レポートを作って", [Fact("変更した。", f"docs/{_IMG}.md")])
    add("<img src=x onerror" not in evil_src, "raw HTML survived in a source label")

    # 9: the escaped document still validates (structure and numbers intact)
    add(validate_document(generate_document("進捗レポートを作って",
                                            facts=[Fact("完了は 42 件。", "docs/s.md")],
                                            now=_NOW),
                          [Fact("完了は 42 件。", "docs/s.md")])["usable"],
        "escaping broke document validation")

    # 10: a document with no HTML is unaffected (no spurious tags, content intact)
    clean = _md("競合分析のレポートを作って", [Fact("競合Aは値下げした。", "docs/m.md")])
    add("競合Aは値下げした" in clean and "&lt;" not in clean,
        "a clean document was disturbed by escaping")

    total = 11
    return DocumentEscapeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DocumentEscapeResult", "evaluate_document_escapes_html_in_evidence"]
