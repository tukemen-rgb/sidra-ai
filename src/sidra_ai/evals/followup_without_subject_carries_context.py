"""Does a subject-less follow-up ground on the topic under discussion?

C-1453: the history-carry retry only fired when the bare follow-up retrieved
*nothing* (「why is that?」). But a Japanese elaboration phrase like 「もっと詳しく」
has no subject term of its own - every bigram carries hiragana glue - so BM25
still fills top_k on a cross-word bigram: 「詳し」 out of 「もっと詳しく」 matched an
unrelated onboarding doc that happened to say 「詳しい手順」. Because results were
non-empty the carry was skipped, and because the phrase names no subject the
honesty floor could not rule on it, so the wrong doc was cited *as the
elaboration* of the previous answer - a confidently off-topic citation, worse
than the honest no-evidence reply.

The carry now also fires when the follow-up names no subject of its own, so it
grounds on the question actually under discussion. A follow-up that does name a
subject, and single-turn retrieval, are left exactly as they were.

The checks build a real ``SidraService`` over a small corpus and read which
document each turn cites.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_DEPLOY = "docs/deploy.md"
_ONBOARD = "docs/onboarding.md"
_MARKETING = "docs/marketing.md"
_DEPLOY_EN = "docs/deploy_en.md"


def _service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import (
        Document,
        Provenance,
        SourceType,
        TrustLevel,
    )
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
    store.add(doc("Deploys require human approval before release.", _DEPLOY_EN))
    return SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)


def _paths(result) -> list[str]:
    return [c["path"] for c in result["citations"]]


@dataclass(frozen=True)
class FollowupSubjectResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_followup_without_subject_carries_context() -> FollowupSubjectResult:
    svc = _service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    q1 = "デプロイの承認は誰がしますか"
    r1 = svc.chat(q1)
    hist = [(q1, r1["answer"])]

    add(_paths(r1)[:1] == [_DEPLOY], f"Q1 did not cite deploy.md: {_paths(r1)}")

    # A subject-less elaboration follow-up grounds on the topic under
    # discussion (deploy), not on whatever doc a glue bigram happened to hit.
    for fu in ("もっと詳しく", "もっと詳しく教えて", "詳しく"):
        paths = _paths(svc.chat(fu, history=hist))
        add(paths[:1] == [_DEPLOY],
            f"elaboration {fu!r} did not ground on deploy.md (first={paths[:1]}, all={paths})")

    # 「続けて」 retrieves nothing on its own too; it must ground on deploy.
    add(_paths(svc.chat("続けて", history=hist))[:1] == [_DEPLOY],
        "「続けて」 did not ground on deploy.md")

    # A follow-up that names a NEW subject is not carried away from it: it
    # grounds on its own subject, and the old topic's doc is not dragged in.
    mk = _paths(svc.chat("マーケティングのレポートは？", history=hist))
    add(mk[:1] == [_MARKETING],
        f"new-subject follow-up was carried off its subject: {mk}")
    add(_DEPLOY not in mk,
        f"new-subject follow-up was over-carried into the old topic: {mk}")

    # Single-turn retrieval with a real subject is unchanged.
    add(_paths(svc.chat("デプロイの承認"))[:1] == [_DEPLOY],
        "single-turn subject query changed")

    # The original empty-result carry (English 「why is that?」) still works.
    why = _paths(svc.chat("why is that?",
                          history=[("does deploy require approval", "yes, it does")]))
    add(_DEPLOY_EN in why, f"English unsearchable follow-up lost its evidence: {why}")

    total = 9
    return FollowupSubjectResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "FollowupSubjectResult",
    "evaluate_followup_without_subject_carries_context",
]
