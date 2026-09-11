"""Does the web UI show the citation excerpt it already receives?

C-1689. ``/v1/chat`` attaches an ``excerpt`` to each citation so a reader can
check the answer against its evidence rather than taking repository, path and
rank on faith (``service._attach_excerpts``). The excerpt is selected, boundary-
opened, truncation-marked, output-guarded and capped - and measured by evals -
but ``ui.py``'s ``render()`` drew only the label, path, the ``redacted`` and
``excerpt_withheld`` flags and the trust level. It surfaced the *absence* of an
excerpt (「抜粋を秘匿」) yet never the excerpt itself, leaving a general user to
trust the answer, the very thing the excerpt exists to prevent.

The checks read the entry-page source (the excerpt is drawn, as text not markup,
guarded on its presence) and drive the real ``/v1/chat`` (a cited answer carries
a non-empty excerpt that is a slice of its source), so a UI that stops showing
the excerpt, or shows it unsafely, or an API that stops producing it, all fail.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone


def _chat_citations(message: str) -> list[dict]:
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    gate = SecurityGate(GatePolicy(), allowed_repositories=("acme/handbook",))
    store = DocumentStore(gate)
    prov = Provenance(
        source="github", repository="acme/handbook", path="faq.md",
        commit_sha="abc1234", timestamp=datetime.now(timezone.utc),
        source_type=SourceType.DOCS, trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )
    store.add(Document(
        content="# 営業時間\n\n本社の定休日は毎週月曜日です。年末年始も休業します。",
        provenance=prov,
    ))
    settings = Settings(data_dir=tempfile.mkdtemp())
    service = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    return client.post("/v1/chat", json={"message": message}).json().get("citations", [])


@dataclass(frozen=True)
class UiExcerptResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_shows_citation_excerpt() -> UiExcerptResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) render() sets the excerpt body as text content (a negative
    #         lookahead so the c.excerpt_withheld flag does not count) ---
    add(re.search(r"textContent\s*=\s*c\.excerpt(?!_withheld)", ASK_PAGE) is not None,
        "A: render() never sets textContent = c.excerpt to draw the excerpt body")

    # --- (B) drawn as text, not markup (no innerHTML introduced) ---
    add("innerHTML" not in ASK_PAGE,
        "B: the page introduced innerHTML - retrieved content must stay DATA")

    # --- (C) a cited answer actually carries a non-empty excerpt of its source ---
    cits = _chat_citations("本社の定休日は？")
    with_excerpt = [c for c in cits if c.get("excerpt")]
    add(bool(with_excerpt) and "定休日" in with_excerpt[0]["excerpt"],
        f"C: /v1/chat returned no excerpt to show (citations={len(cits)})")

    # --- (D) the withheld path is preserved (no regression) ---
    add(re.search(r"c\.excerpt_withheld", ASK_PAGE) is not None,
        "D: the excerpt_withheld handling was lost")

    # --- (E) the excerpt body is drawn only when present (guarded on truthiness) ---
    add(re.search(r"if \(c\.excerpt(?!_withheld)\b", ASK_PAGE) is not None
        or re.search(r"c\.excerpt(?!_withheld)\w*\s*&&", ASK_PAGE) is not None,
        "E: the excerpt is drawn without guarding on its presence (empty block)")

    # --- (F) a short source yields the chunk itself as the excerpt (real
    #         content, not a placeholder), driving the real pipeline ---
    add(bool(with_excerpt) and "本社の定休日は毎週月曜日です" in with_excerpt[0]["excerpt"],
        "F: the excerpt was not the real source content")

    total = 6
    return UiExcerptResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["UiExcerptResult", "evaluate_ui_shows_citation_excerpt"]
