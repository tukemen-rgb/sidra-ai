"""Does the citation excerpt a reader is shown flatten Markdown decoration?

C-1711. ``/v1/chat`` attaches an ``excerpt`` to each citation (``_attach_excerpts``),
and C-1689/1691 surface it to the reader in the web UI and the CLI. But while the
answer text (C-1216) and generator-bound facts (C-1212) flatten Markdown, the
citation excerpt was left raw - an old ``service`` comment said it should "match
the source on review". So a reader who opens a citation to check the answer sees a
wall of ``##``/``**``/table pipes/code fences/``===`` under a clean answer, the
same "reads as broken document text" problem C-1264/1703 already fixed for the
same excerpt's clip and redaction edges. ``_attach_excerpts`` now flattens the
excerpt with ``plain_text`` (which keeps every word, so the words still match the
source), closing the client asymmetry.

The checks drive the real ``/v1/chat`` over a Markdown-heavy document: the shown
excerpt carries no heading, bold, table, fence or setext-underline artifact, its
content words survive (evidence is not lost), and a plain-prose document's excerpt
is unchanged (no over-stripping).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone


def _chat_citation_excerpt(message: str, doc_content: str) -> str:
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    gate = SecurityGate(GatePolicy(), allowed_repositories=("acme/h",))
    store = DocumentStore(gate)
    prov = Provenance(
        source="github", repository="acme/h", path="pricing.md", commit_sha="abc1234",
        timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
    )
    store.add(Document(content=doc_content, provenance=prov))
    settings = Settings(data_dir=tempfile.mkdtemp())
    service = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    citations = client.post("/v1/chat", json={"message": message}).json().get("citations", [])
    for citation in citations:
        if citation.get("excerpt"):
            return str(citation["excerpt"])
    return ""


_MD_DOC = (
    "## 料金プラン\n\n"
    "当社の**料金**は次の表のとおり。\n\n"
    "| プラン | 月額 |\n| --- | --- |\n| 無料 | 0円 |\n| Pro | 1980円 |\n\n"
    "詳しくは `config.yaml` を参照。\n\n"
    "```bash\nsidra-api --port 8787\n```\n\n"
    "まとめ\n===\n\n以上が料金体系の概要です。\n"
)


@dataclass(frozen=True)
class CitationFlattenResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_citation_excerpt_flattens_markdown() -> CitationFlattenResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    ex = _chat_citation_excerpt("料金プランを教えて", _MD_DOC)

    # --- (A) no heading hashes in the shown excerpt ---
    add("##" not in ex and "# " not in ex, f"A: a heading marker survived: {ex!r}")

    # --- (B) no bold stars ---
    add("**" not in ex, f"B: a bold marker survived: {ex!r}")

    # --- (C) the table is flattened: no separator/pipe, but a cell value survives ---
    add("| ---" not in ex and "|" not in ex and "1980円" in ex,
        f"C: the table was not flattened or its content was lost: {ex!r}")

    # --- (D) no code fence artifact (backtick fence removed) ---
    add("```" not in ex and "``" not in ex, f"D: a code fence artifact survived: {ex!r}")

    # --- (E) no setext = underline artifact (consistency with C-1709) ---
    add("===" not in ex and "料金プラン" in ex,
        f"E: a setext underline survived or the heading text was lost: {ex!r}")

    # --- (F) a plain-prose excerpt is unchanged (no over-stripping) ---
    plain_doc = "本社の定休日は毎週月曜日です。"
    plain_ex = _chat_citation_excerpt("定休日はいつですか", plain_doc)
    add(plain_ex == plain_doc, f"F: a plain-prose excerpt was altered: {plain_ex!r}")

    total = 6
    return CitationFlattenResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CitationFlattenResult", "evaluate_citation_excerpt_flattens_markdown"]
