"""Does the web UI link each citation to the source it cites?

C-1735. ``/v1/chat`` attaches a ``url`` to every citation - the ingestion-recorded
address of the cited PR, commit, issue or file - and it is populated for every
source type (a docs citation's url even pins the exact ``blob/<full-sha>/<path>``,
more precise than the compact ``repo@sha:path`` reference). The CLI at least prints
that reference; ``ui.py``'s ``render()`` drew label, path, the redacted and
excerpt_withheld flags, the trust level and the excerpt - but never the url, and it
shows only ``repository + path`` (dropping even the sha). A browser reader, the
surface most people use, therefore could not click through to the source, nor even
reconstruct its address by hand. The excerpt lets them check the words; without a
link they cannot reach the source the citation exists to point at (the sibling of
C-1689, which put the excerpt on the page in the first place).

``render()`` now links the source via a scheme-validated anchor: a new pure helper
``sourceUrl`` passes an http(s) URL through and drops anything else (a citation is
DATA, so a ``javascript:``/``data:`` url is never made clickable), and the link is
built with DOM properties - never markup - and opened with ``rel=noopener``.

The checks extract ``sourceUrl`` and run it in node (http(s) accepted, dangerous and
non-http schemes rejected), read the entry-page source (an anchor is built from the
citation url, guarded, safe, and the page still uses no innerHTML), and drive the
real ``/v1/chat`` (a cited answer carries an http(s) url that ``sourceUrl`` accepts).
"""

from __future__ import annotations

from sidra_ai.evals.scratch import scratch_dir

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone


def _ask_page() -> str:
    from sidra_ai.api.ui import ASK_PAGE

    return ASK_PAGE


def _run_source_url(cases: list[str]) -> list[str] | None:
    """Extract ``sourceUrl`` from the entry page and run it in node on ``cases``.

    Returns ``None`` (rather than raising) when the function is absent or node
    fails, so the broken baseline - before the helper exists - scores RED
    instead of crashing the whole eval run.
    """

    page = _ask_page()
    match = re.search(r"function sourceUrl\(.*?\n  \}", page, re.DOTALL)
    if not match:
        return None
    snippet = match.group(0)
    program = (
        snippet
        + "\nconsole.log(JSON.stringify("
        + json.dumps(cases)
        + ".map(function(u){return sourceUrl(u);})));\n"
    )
    try:
        out = subprocess.run(
            ["node", "-e", program], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


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
        url="https://github.com/acme/handbook/blob/abc1234/faq.md",
    )
    store.add(Document(
        content="# 営業時間\n\n本社の定休日は毎週月曜日です。年末年始も休業します。",
        provenance=prov,
    ))
    settings = Settings(data_dir=scratch_dir())
    service = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    return client.post("/v1/chat", json={"message": message}).json().get("citations", [])


@dataclass(frozen=True)
class UiCitationLinkResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_citation_links_to_source() -> UiCitationLinkResult:
    page = _ask_page()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # sourceUrl("https://…"), ("http://…"), ("javascript:…"), ("data:…"), (""), ("ftp://…")
    https_url = "https://github.com/acme/handbook/pull/17"
    results = _run_source_url(
        [https_url, "http://x/y", "javascript:alert(1)", "data:text/html,x", "", "ftp://h/f"]
    )
    if results is None:
        results = [None] * 6  # helper absent (broken baseline) - A..C fail below
    accepted_https, accepted_http, js, data, empty, ftp = results

    # --- (A) an http(s) URL is passed through unchanged (link target) ---
    add(accepted_https == https_url and accepted_http == "http://x/y",
        f"A: sourceUrl did not pass an http(s) URL through: {accepted_https!r}, {accepted_http!r}")

    # --- (B) a javascript: URL is dropped (DATA never becomes a live scheme) ---
    add(js == "", f"B: sourceUrl did not drop a javascript: URL: {js!r}")

    # --- (C) other non-http schemes and the empty string are dropped ---
    add(data == "" and empty == "" and ftp == "",
        f"C: sourceUrl kept a non-http URL: data={data!r} empty={empty!r} ftp={ftp!r}")

    # --- (D) render() builds an anchor from the citation url via sourceUrl,
    #         guarded on there being a safe URL ---
    add(re.search(r"sourceUrl\(c\.url\)", page) is not None
        and re.search(r'createElement\("a"\)', page) is not None
        and re.search(r"\.href\s*=", page) is not None,
        "D: render() does not build an anchor from sourceUrl(c.url)")

    # --- (E) the link is opened safely and nothing is rendered as markup.
    #         The rel is checked as a real assignment, not the substring: a
    #         comment mentioning noopener must not stand in for setting it. ---
    add(re.search(r'\.rel\s*=\s*"[^"]*noopener', page) is not None
        and "innerHTML" not in page,
        "E: the source link is missing a rel=noopener assignment, or the page introduced innerHTML")

    # --- (F) a real cited answer carries an http(s) url that sourceUrl accepts ---
    cits = _chat_citations("本社の定休日は？")
    with_url = [c for c in cits if c.get("url")]
    end_to_end = None
    if with_url and results[0] is not None:
        end_to_end = _run_source_url([with_url[0]["url"]])
    add(bool(with_url) and re.match(r"^https?://", with_url[0]["url"]) is not None
        and end_to_end is not None and end_to_end[0] == with_url[0]["url"],
        f"F: /v1/chat gave no http(s) url sourceUrl accepts (citations={len(cits)})")

    total = 6
    return UiCitationLinkResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["UiCitationLinkResult", "evaluate_ui_citation_links_to_source"]
