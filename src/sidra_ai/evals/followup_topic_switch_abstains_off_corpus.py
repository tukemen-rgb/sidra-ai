"""Does a mid-conversation switch to an uncovered subject abstain, not bleed?

C-1481. The history-carry (C-1453) fires when a follow-up retrieves nothing, so
a follow-up that names a NEW subject the corpus does not cover ("料金プランは？"
after a deploy question) pulled the previous topic's documents, and the honesty
floor then passed them because the concatenated query still matches the
*previous* subject. The user, who changed topics, got the old answer to a new
question - worse than the honest no-evidence reply the same question gives with
no history.

The floor now also abstains when the carry happened, the follow-up has its own
content subject (its subject terms minus interrogatives like why/how/what), and
the evidence mentions none of it. A pure elaboration with no content subject of
its own ("why is that?", 「もっと詳しく」, 「続けて」) still carries; a new subject the
corpus *does* cover still grounds on itself.

The checks build a real ``SidraService`` and read which document each turn cites.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_DEPLOY = "docs/deploy.md"
_MARKETING = "docs/marketing.md"
_DEPLOY_EN = "docs/deploy_en.md"


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
    gate = SecurityGate(GatePolicy(), allowed_repositories=allowed,
                        quarantine_store=QuarantineStore(tmp / "q.jsonl"))
    store = DocumentStore(gate)

    def doc(content: str, path: str) -> Document:
        return Document(content=content, provenance=Provenance(
            source="github", repository="tukemen-rgb/site", path=path,
            commit_sha="c" * 40, timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS, trust_level=TrustLevel.INTERNAL_REPO, license="MIT"))

    # Two covered topics; no pricing (料金) document anywhere.
    store.add(doc("デプロイは必ず運用者の承認を得てから実行する。承認者は当番のリードエンジニアが務める。", _DEPLOY))
    store.add(doc("マーケティングの週次レポートは毎週金曜に更新する。閲覧は社内限定。", _MARKETING))
    store.add(doc("Deploys require human approval before release.", _DEPLOY_EN))
    return SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)


def _paths(result) -> list[str]:
    return [c["path"] for c in result["citations"]]


def _abstains(result) -> bool:
    return not result["citations"] and "十分な根拠がありません" in result["answer"]


@dataclass(frozen=True)
class TopicSwitchResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_followup_topic_switch_abstains_off_corpus() -> TopicSwitchResult:
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
    add(_paths(r1)[:1] == [_DEPLOY], f"Q1 did not cite deploy: {_paths(r1)}")

    # topic switch to an uncovered subject, with history: abstain, no bleed.
    off = svc.chat("料金プランを教えて", history=hist)
    add(_abstains(off), f"off-corpus switch did not abstain: cites={_paths(off)}")
    add(_DEPLOY not in _paths(off), f"off-corpus switch bled the deploy topic: {_paths(off)}")
    add("承認" not in off["answer"], "off-corpus switch answer carried the deploy content")

    # the same question with no history already abstains - the fix keeps parity.
    add(_abstains(svc.chat("料金プランを教えて")), "single-turn off-corpus stopped abstaining")

    # a pure elaboration still carries onto the topic under discussion.
    for fu in ("もっと詳しく", "続けて"):
        add(_paths(svc.chat(fu, history=hist))[:1] == [_DEPLOY],
            f"elaboration {fu!r} no longer grounds on deploy: {_paths(svc.chat(fu, history=hist))}")

    # an English unsearchable follow-up ("why is that?") still keeps its evidence.
    why = _paths(svc.chat("why is that?",
                          history=[("does deploy require approval", "yes, it does")]))
    add(_DEPLOY_EN in why, f"English elaboration lost its evidence: {why}")

    # a new subject the corpus DOES cover still grounds on itself, not the old topic.
    mk = svc.chat("マーケティングのレポートは？", history=hist)
    add(_paths(mk)[:1] == [_MARKETING], f"covered new subject misrouted: {_paths(mk)}")
    add(_DEPLOY not in _paths(mk), f"covered new subject over-carried deploy: {_paths(mk)}")

    total = 10
    return TopicSwitchResult(passed=not failures, checks_passed=checks,
                             checks_total=total, failures=tuple(failures))


__all__ = ["TopicSwitchResult", "evaluate_followup_topic_switch_abstains_off_corpus"]
