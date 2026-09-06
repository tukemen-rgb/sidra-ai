"""Does a deck say when the PowerPoint file could not be made?

C-1274: ``save_pptx`` needs python-pptx, an optional ``creation`` extra. Where it
is not installed (a legitimate, shippable state), every deck falls back to HTML
only - and the summary still said 「『売上』を 4 枚で作りました」, naming no word
that the .pptx was skipped. The fact was carried in ``details.pptx_path=""`` for a
caller, but the person who asked for slides read only the summary and received
HTML without knowing. The summary now says so when the .pptx was not written, and
stays silent when it was.

Environment-robust by construction: each check reads ``details.pptx_path`` and
asserts the disclosure is present exactly when the file is absent, so the eval
holds whether or not python-pptx is installed.

Measured through the real chat path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

#: The disclosure the summary must carry when no .pptx was written.
_NOTE_MARKER = "PowerPoint（.pptx）は作れなかった"

#: Deck requests: one that retrieves facts (a filled deck) and one that does not
#: (an empty frame). Both must disclose an absent .pptx.
_REQUESTS: tuple[str, ...] = (
    "売上のスライドを作って",
    "事業計画のスライドを作って",
)


@dataclass(frozen=True)
class DeckPptxAbsenceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(tempfile.mkdtemp(prefix="deck-pptx-"))
    repo = "tukemen-rgb/sidra-ai"
    settings = Settings(allowed_repositories=(repo,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repo,),
        quarantine_store=QuarantineStore(tmp / "q.jsonl"),
    )
    store = DocumentStore(gate)

    def prov(path: str) -> Provenance:
        return Provenance(
            source="github", repository=repo, path=path, commit_sha="d" * 40,
            timestamp=datetime(2026, 9, 3, tzinfo=timezone.utc),
            source_type=SourceType.DOCS, trust_level=TrustLevel.INTERNAL_REPO,
            license="proprietary",
        )

    for i, content in enumerate(
        ["売上は前年比120%で着地しました。", "売上の月間平均は1200万円です。"]
    ):
        store.add(Document(content=content, provenance=prov(f"docs/uriage-{i}.md")))
    return SidraService(settings, store=store, gate=gate)


def evaluate_deck_pptx_absence_disclosed() -> DeckPptxAbsenceResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request in _REQUESTS:
        result = service.chat(request) or {}
        creation = result.get("creation") or {}
        outcome = creation.get("outcome") or {}
        kind = (creation.get("intent") or {}).get("kind")
        if not (outcome.get("handled") and kind == "deck"):
            failures.append(f"{request!r}: did not route to deck (kind={kind})")
            continue
        answer = str(result.get("answer") or "")
        pptx_written = bool((outcome.get("details") or {}).get("pptx_path"))
        if pptx_written:
            # python-pptx is installed here: no disclosure is due.
            add(_NOTE_MARKER not in answer,
                f"{request!r}: disclosed an absent .pptx though one was written")
        else:
            # HTML-only fallback: the summary must say the .pptx was skipped.
            add(_NOTE_MARKER in answer,
                f"{request!r}: no .pptx-absence disclosure in 「{answer}」")

    total = len(_REQUESTS)
    return DeckPptxAbsenceResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DeckPptxAbsenceResult", "evaluate_deck_pptx_absence_disclosed"]
