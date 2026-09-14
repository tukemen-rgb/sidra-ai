"""Does a document say when it could not make the file format that was asked for?

C-1834, the document twin of the deck's C-1465. A request that names a file
format the document generator does not produce - 「売上のレポートをWordで作って」,
「…をPDFで」, 「…をExcelで」 - got a Markdown file and a summary that named only
Markdown (「Markdown なのでそのまま編集・貼り付けできます」), never that the Word/PDF
the operator asked for was not made. The deck already discloses the analogue
(「PowerPoint（.pptx）は作れなかったので HTML のみ」); the document, which only ever
writes Markdown by design, said nothing, so a reader who asked for Word believed
they would open Word. The summary now names the requested format and that it
could not be made, and stays silent when no format was named or when a
format-looking word is the subject rather than the requested output.

Measured through the real chat path, both directions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

_REPO = "acme/app"
#: The phrase the summary carries when a requested format cannot be produced.
_NOTE = "形式では作れない"


def _service() -> SidraService:
    tmp = scratch_dir()
    gate = SecurityGate(
        GatePolicy(), allowed_repositories=(_REPO,),
        quarantine_store=QuarantineStore(os.path.join(tmp, "q.jsonl")),
    )
    store = DocumentStore(gate)

    def add(path: str, content: str) -> None:
        store.add(Document(
            content=content,
            provenance=Provenance(
                source="github", repository=_REPO, path=path, commit_sha="a" * 7,
                timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
                trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
            ),
        ))

    add("sales.md", "売上は前年比120%で成長した。")
    add("pdfops.md", "PDFで管理する方法はこの手順書に書かれている。")
    add("wordtips.md", "Wordの使い方はこの資料にまとまっている。")
    return SidraService(
        Settings(allowed_repositories=(_REPO,), data_dir=os.path.join(tmp, "sidra")),
        store=store, gate=gate,
    )


def _summary(svc: SidraService, request: str) -> str:
    r = svc.chat(request) or {}
    return str((r.get("creation") or {}).get("outcome", {}).get("summary") or r.get("answer") or "")


@dataclass(frozen=True)
class DocumentFormatSubstitutionResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_discloses_format_substitution() -> DocumentFormatSubstitutionResult:
    svc = _service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # Disclose: a named, unproducible format.
    for request, label in (
        ("売上のレポートをWordで作って", "Word"),
        ("売上のレポートをPDFで作って", "PDF"),
        ("売上のレポートをExcelで作って", "Excel"),
    ):
        s = _summary(svc, request)
        add(_NOTE in s and label in s,
            f"{request!r}: summary omits the {label} substitution note: {s[:90]!r}")

    # Stay silent: no format named, or a format-looking word that is the subject.
    for request in (
        "売上のレポートを作って",
        "PDFで管理する方法のレポートを作って",
        "Wordの使い方のレポートを作って",
    ):
        s = _summary(svc, request)
        add(_NOTE not in s,
            f"{request!r}: summary wrongly carries a format substitution note: {s[:90]!r}")

    total = 6
    return DocumentFormatSubstitutionResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DocumentFormatSubstitutionResult",
    "evaluate_document_discloses_format_substitution",
]
