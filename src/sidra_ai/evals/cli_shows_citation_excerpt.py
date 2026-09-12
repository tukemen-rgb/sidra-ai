"""Does the sidra-ask CLI show the citation excerpt, like the web UI does?

C-1691. C-1689 taught the web UI to draw the excerpt each citation carries so a
reader can check the answer against its evidence. Its sibling, the CLI's
``_print_citations``, was left behind: it printed label, reference and the
``一部秘匿``/``抜粋を秘匿``/trust marks, but never the excerpt body - it surfaced
the *absence* of an excerpt yet not the excerpt itself, the same asymmetry C-1689
closed for the browser. The CLI now prints the excerpt, terminal-scrubbed, on its
own indented line beneath the citation.

The checks capture ``render``'s stdout: a cited answer prints its excerpt, a
terminal control sequence in an excerpt is stripped, a withheld excerpt still
reads as ``抜粋を秘匿`` with no body, and an empty excerpt adds no stray line.
"""

from __future__ import annotations

import contextlib
import io
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone


def _render(payload: dict) -> str:
    from sidra_ai.api.ask_cli import render

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        render(payload)
    return buf.getvalue()


def _cite(**over) -> dict:
    base = {
        "label": "S1", "citation": "acme/handbook@abc1234:faq.md",
        "repository": "acme/handbook", "path": "faq.md", "commit_sha": "abc1234",
        "source_type": "docs", "trust_level": "internal_repo", "license": "x",
        "redacted": False, "excerpt": "", "excerpt_withheld": False,
    }
    base.update(over)
    return base


def _answer_payload(citations: list[dict]) -> dict:
    return {"answer": "回答本文。", "refused": False, "citations": citations}


def _real_chat_citations() -> list[dict]:
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
    store.add(Document(content="# 営業時間\n\n本社の定休日は毎週月曜日です。", provenance=prov))
    settings = Settings(data_dir=tempfile.mkdtemp())
    service = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    return client.post("/v1/chat", json={"message": "本社の定休日は？"}).json().get("citations", [])


@dataclass(frozen=True)
class CliExcerptResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_shows_citation_excerpt() -> CliExcerptResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) a citation's excerpt body is printed ---
    out_a = _render(_answer_payload([_cite(excerpt="本社の定休日は毎週月曜日です。")]))
    add("本社の定休日は毎週月曜日です。" in out_a,
        "A: the excerpt body was not printed by the CLI")

    # --- (B) a terminal control sequence in an excerpt is stripped ---
    out_b = _render(_answer_payload([_cite(excerpt="\x1b[31m危険\x1b[0m 本社の定休日")]))
    add("本社の定休日" in out_b and "\x1b" not in out_b,
        "B: excerpt was not terminal-scrubbed before printing")

    # --- (C) a withheld excerpt still reads as 抜粋を秘匿 with no body (no regression) ---
    out_c = _render(_answer_payload([_cite(excerpt="", excerpt_withheld=True)]))
    add("抜粋を秘匿" in out_c, "C: the withheld marker was lost")

    # --- (D) a real /v1/chat answer prints a slice of its source ---
    real = _real_chat_citations()
    out_d = _render(_answer_payload(real)) if real else ""
    add(bool(real) and "定休日" in out_d,
        f"D: a real cited answer printed no excerpt (citations={len(real)})")

    # --- (E) an empty excerpt adds no stray whitespace-only line ---
    out_e = _render(_answer_payload([_cite(excerpt="")]))
    stray = [ln for ln in out_e.splitlines() if ln and not ln.strip()]
    add(not stray, f"E: an empty excerpt printed a stray blank line ({len(stray)})")

    # --- (F) the excerpt is printed on its own indented line, not glued to the
    #         reference ---
    add(re.search(r"^\s+本社の定休日は毎週月曜日です。\s*$", out_a, re.M) is not None,
        "F: the excerpt was not on its own indented line")

    total = 6
    return CliExcerptResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliExcerptResult", "evaluate_cli_shows_citation_excerpt"]
