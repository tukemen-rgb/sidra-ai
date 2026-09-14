"""Do a generated document and deck disclose an external/unverified source?

C-1831. The /v1/chat citation flags a source's trust level - 「外部」 for a
third-party-authored Issue/PR/web body, 「未検証」 for one that could not be
attributed (C-1471, shown in the web UI and CLI). But the *forwardable*
artifacts - the report .md and the deck HTML a reader opens and passes on - named
only the repository and path. So an external, unverified user claim from an Issue
(「競合はうちより3倍速いとユーザーが主張」) was printed under 「わかっていること」/
「根拠となる数字」 beside a bare source path, indistinguishable from an
internal-repo fact - the executive who forwarded the report read a third party's
unverified claim as an established, in-house finding. The artifact now carries
the same trust note the chat citation does, and only for a non-internal source,
so an ordinary internal fact is unchanged.

Measured through the real ``SidraService.chat`` over both artifact kinds and both
directions: an external/unverified fact's artifact carries the note; an
internal-repo fact's artifact does not.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

_REPO = "acme/app"
_EXTERNAL_MARK = "外部"
_UNVERIFIED_MARK = "未検証"
#: A claim carrying a number, so it lands on the deck's 「根拠となる数字」 slide.
_CLAIM = "競合製品Xはうちより3倍速いと利用者が主張している。"


def _service(trust: TrustLevel, source_type: SourceType, path: str) -> SidraService:
    tmp = scratch_dir()
    gate = SecurityGate(
        GatePolicy(), allowed_repositories=(_REPO,),
        quarantine_store=QuarantineStore(os.path.join(tmp, "q.jsonl")),
    )
    store = DocumentStore(gate)
    store.add(Document(
        content=_CLAIM,
        provenance=Provenance(
            source="github", repository=_REPO, path=path, commit_sha="a" * 7,
            timestamp=datetime.now(timezone.utc), source_type=source_type,
            trust_level=trust, license="proprietary",
        ),
    ))
    return SidraService(
        Settings(allowed_repositories=(_REPO,), data_dir=os.path.join(tmp, "sidra")),
        model=EchoModelAdapter(), store=store, gate=gate,
    )


def _artifact_text(trust: TrustLevel, source_type: SourceType, path: str, request: str) -> str:
    svc = _service(trust, source_type, path)
    out = (svc.chat(request) or {}).get("creation", {}).get("outcome", {}) or {}
    p = out.get("artifact_path")
    if not p or not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as fh:
        return fh.read()


@dataclass(frozen=True)
class ArtifactTrustResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_generated_artifact_discloses_source_trust() -> ArtifactTrustResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def note_on_claim_line(text: str, note: str) -> bool:
        # The note must sit on the line that states the claim (the 「わかって
        # いること」 bullet / the deck's evidence line), not merely somewhere in
        # the artifact - a reader judges the claim where it is asserted, so the
        # 出典 list carrying it is not enough on its own.
        for line in text.splitlines():
            if _CLAIM[:8] in line:
                return note in line
        return False

    ext_doc = _artifact_text(TrustLevel.EXTERNAL, SourceType.ISSUE, "issues/42", "競合のレポートを作って")
    int_doc = _artifact_text(TrustLevel.INTERNAL_REPO, SourceType.DOCS, "docs/competitor.md", "競合のレポートを作って")
    unv_doc = _artifact_text(TrustLevel.UNVERIFIED, SourceType.WEB, "web/post", "競合のレポートを作って")
    ext_deck = _artifact_text(TrustLevel.EXTERNAL, SourceType.ISSUE, "issues/42", "競合のスライドを作って")
    int_deck = _artifact_text(TrustLevel.INTERNAL_REPO, SourceType.DOCS, "docs/competitor.md", "競合のスライドを作って")

    # The claim must be present (the artifact was actually built from it), else
    # a "no mark" check would pass vacuously.
    add(_CLAIM[:8] in ext_doc, f"A0: external document did not carry the claim: {ext_doc[:60]!r}")
    add(note_on_claim_line(ext_doc, _EXTERNAL_MARK),
        "A: external document omits the 外部 note on the claim bullet")
    add(_EXTERNAL_MARK not in int_doc and _UNVERIFIED_MARK not in int_doc,
        "B: internal document wrongly carries a trust note")
    add(_UNVERIFIED_MARK in unv_doc, "C: unverified document omits the 未検証 note")
    add(_CLAIM[:8] in ext_deck, f"D0: external deck did not carry the claim: {ext_deck[:60]!r}")
    add(_EXTERNAL_MARK in ext_deck, "D: external deck omits the 外部 note")
    add(_EXTERNAL_MARK not in int_deck and _UNVERIFIED_MARK not in int_deck,
        "E: internal deck wrongly carries a trust note")

    total = 7
    return ArtifactTrustResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ArtifactTrustResult",
    "evaluate_generated_artifact_discloses_source_trust",
]
