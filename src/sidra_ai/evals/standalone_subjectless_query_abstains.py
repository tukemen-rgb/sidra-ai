"""Does a subject-less query with no history abstain instead of citing glue?

C-1468, the standalone twin of C-1453. C-1453 made a subject-less *follow-up*
(「もっと詳しく」) carry the previous question so it grounds on the topic under
discussion. But the very same phrase as a *first* message - or after the client
dropped the conversation history - has no previous question to carry and no
subject of its own, so ``subject_terms`` is empty. BM25 still fills top_k on a
generic glue-derived token (「詳し」 out of 「詳しく」 hitting an unrelated
onboarding doc that says 「詳しい手順」), and because the phrase names no subject
the honesty floor returned True and cited that doc as fact - a confidently
off-topic citation, worse than the honest no-evidence reply that 「続けて」
「教えて」 already get.

The floor now abstains when the searched query still names no subject after any
history carry: there is nothing to ground on. A query that names a subject, and
the with-history carry, are left exactly as they were.

The checks build a real ``SidraService`` over a small corpus and read which
document each turn cites (an empty citation list is the honest abstention).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_DEPLOY = "docs/deploy.md"
_ONBOARD = "docs/onboarding.md"
_MARKETING = "docs/marketing.md"


def _service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    allowed = ("tukemen-rgb/site",)
    tmp = Path(tempfile.mkdtemp())
    settings = Settings(allowed_repositories=allowed, data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=allowed,
        quarantine_store=QuarantineStore(tmp / "q.jsonl"),
    )
    store = DocumentStore(gate)

    def doc(content: str, path: str) -> Document:
        return Document(
            content=content,
            provenance=Provenance(
                source="github",
                repository="tukemen-rgb/site",
                path=path,
                commit_sha="c" * 40,
                timestamp=datetime.now(timezone.utc),
                source_type=SourceType.DOCS,
                trust_level=TrustLevel.INTERNAL_REPO,
                license="MIT",
            ),
        )

    store.add(doc("デプロイは必ず運用者の承認を得てから実行する。承認者は当番のリードエンジニアが務める。", _DEPLOY))
    store.add(doc("オンボーディング資料の詳しい手順は入社時に配布する。", _ONBOARD))
    store.add(doc("マーケティングの週次レポートは毎週金曜に更新する。閲覧は社内限定。", _MARKETING))
    return SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)


def _paths(result) -> list[str]:
    return [c["path"] for c in result["citations"]]


@dataclass(frozen=True)
class StandaloneSubjectlessResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_standalone_subjectless_query_abstains() -> StandaloneSubjectlessResult:
    svc = _service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A subject-less phrase as a first message (no history) whose only BM25 hit
    # is a generic glue token must abstain, not cite the doc it grazed.
    for q in ("もっと詳しく", "詳しく教えて", "詳しく"):
        paths = _paths(svc.chat(q))
        add(paths == [],
            f"standalone {q!r} cited a doc instead of abstaining: {paths}")

    # Subject-less phrases that already retrieved nothing still abstain.
    for q in ("続けて", "教えて"):
        add(_paths(svc.chat(q)) == [],
            f"standalone {q!r} stopped abstaining")

    # A standalone query that names a real subject is unchanged.
    add(_paths(svc.chat("デプロイの承認は誰がしますか"))[:1] == [_DEPLOY],
        "single-turn deploy question changed")
    add(_paths(svc.chat("マーケティングのレポートは？"))[:1] == [_MARKETING],
        "single-turn marketing question changed")

    # The C-1453 with-history carry is untouched: an elaboration follow-up
    # still grounds on the topic under discussion rather than abstaining.
    q1 = "デプロイの承認は誰がしますか"
    hist = [(q1, svc.chat(q1)["answer"])]
    add(_paths(svc.chat("もっと詳しく", history=hist))[:1] == [_DEPLOY],
        "with-history elaboration no longer carries context (C-1453 regressed)")

    total = 3 + 2 + 2 + 1
    return StandaloneSubjectlessResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "StandaloneSubjectlessResult",
    "evaluate_standalone_subjectless_query_abstains",
]
