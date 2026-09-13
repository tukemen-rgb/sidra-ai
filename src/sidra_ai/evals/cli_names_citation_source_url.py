"""Does the sidra-ask CLI show the citation's source URL, like the web UI does?

C-1742. C-1735 taught the web UI to render each citation's ``url`` as a clickable
link so a reader can open the cited PR/commit/file and check the answer at its
origin. Its sibling, the CLI's ``_print_citations``, was left behind (C-1735
explicitly deferred it): it prints label, reference, the redaction/withheld/trust
marks and the excerpt, but never the ``url``. The reference (``repo@sha7:path``)
is navigable by hand, but the ``url`` is the exact, copy-pasteable address the
service already carries - and for a docs source it pins ``blob/<full-sha>/<path>``,
more precise than the 7-char reference. The CLI now prints it, terminal-scrubbed,
on its own indented line, only for an http(s) URL.

The checks capture ``render``'s stdout: a citation with an http(s) url prints it
on its own line, a control sequence in the url is stripped, a url-less citation
adds no stray line, a non-http scheme is not shown as a source, and a real
``/v1/chat`` answer prints the url its source carries.
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
        "redacted": False, "excerpt": "", "excerpt_withheld": False, "url": "",
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
        url="https://github.com/acme/handbook/blob/abc1234/faq.md",
    )
    store.add(Document(content="# 営業時間\n\n本社の定休日は毎週月曜日です。", provenance=prov))
    settings = Settings(data_dir=tempfile.mkdtemp())
    service = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    return client.post("/v1/chat", json={"message": "本社の定休日は？"}).json().get("citations", [])


@dataclass(frozen=True)
class CliCitationUrlResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_names_citation_source_url() -> CliCitationUrlResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    url = "https://github.com/acme/handbook/pull/17"

    # --- (A) a citation's http(s) url is printed ---
    out_a = _render(_answer_payload([_cite(url=url)]))
    add(url in out_a, "A: the citation url was not printed by the CLI")

    # --- (B) the url is on its own indented line, not glued to the reference ---
    add(re.search(rf"^\s+.*{re.escape(url)}\s*$", out_a, re.M) is not None,
        "B: the url was not on its own indented line")

    # --- (C) a terminal control sequence in the url is stripped ---
    out_c = _render(_answer_payload([_cite(url="https://ex.com/\x1b[31mp")]))
    add("https://ex.com/" in out_c and "\x1b" not in out_c,
        "C: the url was not terminal-scrubbed before printing")

    # --- (D) a url-less citation adds no stray source line (no over-printing) ---
    out_d = _render(_answer_payload([_cite(url="")]))
    add("出典:" not in out_d, f"D: a url-less citation printed a stray source line: {out_d!r}")

    # --- (E) a non-http scheme is not shown as a source link (DATA safety) ---
    out_e = _render(_answer_payload([_cite(url="javascript:alert(1)")]))
    add("javascript:" not in out_e,
        f"E: a non-http url was printed as a source: {out_e!r}")

    # --- (F) a real /v1/chat answer prints the url its source carries ---
    real = _real_chat_citations()
    out_f = _render(_answer_payload(real)) if real else ""
    with_url = [c for c in real if c.get("url")]
    add(bool(with_url) and with_url[0]["url"] in out_f,
        f"F: a real cited answer printed no source url (citations={len(real)})")

    total = 6
    return CliCitationUrlResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliCitationUrlResult", "evaluate_cli_names_citation_source_url"]
