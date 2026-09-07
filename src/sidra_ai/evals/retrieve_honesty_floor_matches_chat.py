"""Does /v1/retrieve abstain on all-glue matches the way /v1/chat does?

C-1477. ``chat()`` carries the C-1468/C-1453 honesty floor: CJK bigram scoring
fills ``top_k`` even when the corpus knows nothing about the subject (「天気を
教えて」 matched five chunks on 「を教」-shaped glue), so when the query names no
subject term, or no retrieved chunk mentions the subject, the results are dropped
and the honest no-evidence answer is given. ``retrieve()`` - the source-discovery
endpoint - had no such floor: it returned whatever BM25 ranked, so a query about
something the corpus does not cover came back with glue-matched documents
presented as the sources for it. The same product then abstained in chat and
misled in retrieve.

``retrieve()`` now applies the same floor. A query whose subject the evidence
carries still returns its sources; ranking and ``min_score`` are untouched.

The checks build a real service over a small glue-rich corpus and compare the
two endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Glue-rich corpus (について/詳しく/教え/ください) about marketing and
# architecture only - nothing about space travel or resignation procedures.
_README = (
    "SIDRA STUDIO の広告サイトについて詳しく説明します。"
    "料金ページの構成について教えます。事例ページの使い方も詳しく案内します。"
    "お問い合わせについては下記をご覧ください。導入手順について順に説明します。"
)
_ARCH = (
    "本システムの構成について詳しく述べます。索引の仕組みについて教えます。"
    "検索の流れについて詳しく説明します。運用についてはこちらをご覧ください。"
    "設定項目について順に案内します。ログ収集について詳しく記します。"
)

_OFF_CORPUS = (
    "宇宙旅行について詳しく教えてください",
    "退職手続きについて教えてください",
    "もっと詳しく教えてください",  # no subject term of its own
)
_IN_CORPUS = (
    "料金ページについて教えて",
    "アーキテクチャの構成について教えて",
)


def _service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(tempfile.mkdtemp(prefix="retrieve-floor-"))
    repo = "tukemen-rgb/site"
    settings = Settings(allowed_repositories=(repo,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repo,),
        quarantine_store=QuarantineStore(tmp / "q.jsonl"),
    )
    store = DocumentStore(gate)
    for path, body in (("README.md", _README), ("docs/arch.md", _ARCH)):
        prov = Provenance(
            source="github", repository=repo, path=path, commit_sha="a" * 40,
            timestamp=datetime(2026, 9, 7, tzinfo=timezone.utc),
            source_type=SourceType.DOCS, trust_level=TrustLevel.INTERNAL_REPO,
            license="proprietary",
        )
        store.add(Document(content=body, provenance=prov))
    return SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)


@dataclass(frozen=True)
class RetrieveFloorResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_retrieve_honesty_floor_matches_chat() -> RetrieveFloorResult:
    svc = _service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def _abstains_chat(q: str) -> bool:
        return not svc.chat(q, top_k=5)["citations"]

    # off-corpus / subjectless: retrieve returns nothing, is not a gate refusal,
    # and gives the honest no-evidence reason - matching chat's abstention.
    for q in _OFF_CORPUS:
        r = svc.retrieve(q, top_k=5)
        add(not r["results"], f"off-corpus {q!r}: retrieve returned glue matches")
        add(r["refused"] is False, f"off-corpus {q!r}: retrieve reported a refusal")
    add(all(_abstains_chat(q) for q in _OFF_CORPUS),
        "chat no longer abstains on the off-corpus queries")
    off = svc.retrieve(_OFF_CORPUS[0], top_k=5)
    add(off["reason"] == "no indexed evidence matched the query",
        "off-corpus retrieve dropped the honest no-evidence reason")

    # in-corpus subject: retrieve still returns its sources (floor not over-eager),
    # and chat still cites them - the two endpoints agree on the positive case.
    for q in _IN_CORPUS:
        r = svc.retrieve(q, top_k=5)
        add(bool(r["results"]), f"in-corpus {q!r}: retrieve wrongly returned nothing")
    add(bool(svc.chat(_IN_CORPUS[0], top_k=5)["citations"]),
        "in-corpus chat returned no citations (corpus/parity broke)")

    total = 11
    return RetrieveFloorResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["RetrieveFloorResult", "evaluate_retrieve_honesty_floor_matches_chat"]
