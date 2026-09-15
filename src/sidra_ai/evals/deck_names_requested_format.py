"""Does a deck asked for in a document format name THAT format, not PowerPoint?

C-1838, the deck-summary twin of C-1834. A deck request that names a document
format the deck cannot produce - 「スライドをPDFで作って」「…をWordで」 - still got
the fixed PowerPoint notice (「PowerPoint（.pptx）は作れなかったので HTML のみ」).
That names a format the operator never asked for, so it reads as if the request
was misread: someone who typed 「PDFで」 is told about PowerPoint. The document
already names the format actually requested (C-1834). The deck summary now names
it too - 「なお PDF 形式では作れないため、HTML で保存しています。」 - and keeps the
PowerPoint notice only when no document format was named (a plain deck, or one
asked for in パワポ/pptx, still surfaces the .pptx fallback, C-1274).

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
_DOC_NOTE = "形式では作れないため、HTML"
_PPTX_NOTE = "PowerPoint（.pptx）は作れなかった"


def _service() -> SidraService:
    tmp = scratch_dir()
    gate = SecurityGate(
        GatePolicy(), allowed_repositories=(_REPO,),
        quarantine_store=QuarantineStore(os.path.join(tmp, "q.jsonl")),
    )
    store = DocumentStore(gate)
    store.add(Document(
        content="売上は前年比120%で成長した。",
        provenance=Provenance(
            source="github", repository=_REPO, path="sales.md", commit_sha="a" * 7,
            timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
        ),
    ))
    return SidraService(
        Settings(allowed_repositories=(_REPO,), data_dir=os.path.join(tmp, "sidra")),
        store=store, gate=gate,
    )


def _summary(svc: SidraService, request: str) -> str:
    r = svc.chat(request) or {}
    return str((r.get("creation") or {}).get("outcome", {}).get("summary") or r.get("answer") or "")


@dataclass(frozen=True)
class DeckNamesFormatResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_names_requested_format() -> DeckNamesFormatResult:
    svc = _service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A named document format: name it, and drop the PowerPoint notice that would
    # otherwise name a format the operator never asked for.
    for request, label in (
        ("売上のスライドをPDFで作って", "PDF"),
        ("売上のスライドをWordで作って", "Word"),
        ("売上のスライドをExcelで作って", "Excel"),
    ):
        s = _summary(svc, request)
        add(_DOC_NOTE in s and label in s, f"{request!r}: summary omits the {label} note: {s[:110]!r}")
        add(_PPTX_NOTE not in s, f"{request!r}: summary still names PowerPoint the operator did not ask for: {s[:110]!r}")

    # No document format named (a plain deck, or パワポ/pptx): the .pptx fallback
    # notice stands (C-1274), and no document-format note appears.
    for request in ("売上のスライドを作って", "売上のスライドをパワポで作って"):
        s = _summary(svc, request)
        add(_PPTX_NOTE in s and _DOC_NOTE not in s,
            f"{request!r}: expected the .pptx notice and no doc-format note: {s[:110]!r}")

    total = 8
    return DeckNamesFormatResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DeckNamesFormatResult", "evaluate_deck_names_requested_format"]
