"""Does a subject-less follow-up's answer BODY show the passage under discussion?

C-1828. C-1782 made the citation excerpt query-relevant, and C-1827 made the
answer body query-relevant - but the answer body was fed the bare turn, not the
query retrieval actually used. On a follow-up that carries the previous question
(「もっと詳しく」→ ``searched_query``), the bare turn names no subject, so the
answer body's ``_lead`` scored every sentence zero and fell back to the chunk
opening - handing the reader background prose while the sentence that answers
their carried question showed only in the citation excerpt below (which C-1782
already selects with ``searched_query``). The service now passes the effective
retrieval query to the model, so the answer body opens on the same passage the
excerpt does. On a single turn the effective query equals the turn, so ordinary
answers are unchanged.

Measured through the real ``SidraService.chat`` with the echo backend: a direct
question's body shows the subject (baseline), and a subject-less follow-up's body
shows it too instead of the chunk opening.
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

_REPO = "tukemen-rgb/site"
#: Opening filler longer than one block's budget, so the subject sentence that
#: follows it is not in the opening the query-blind body fell back to.
_FILLER = "この文書は運用全般の背景を説明します。歴史的な経緯や関係者の話が続きます。" * 8
_SUBJECT_SENTENCE = (
    "デプロイはmainへのpushで自動的に走り、所要時間はおよそ5分です。"
    "失敗時は自動でロールバックされます。"
)
_CONTENT = _FILLER + _SUBJECT_SENTENCE + "その後の注意事項がさらに続きます。" * 3
#: A token that lives only in the answering sentence, never in the filler.
_ANSWER_MARK = "ロールバック"


@dataclass(frozen=True)
class AnswerBodyCarriesSubjectResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> SidraService:
    tmp = scratch_dir()
    settings = Settings(allowed_repositories=(_REPO,), data_dir=os.path.join(tmp, "sidra"))
    gate = SecurityGate(
        GatePolicy(), allowed_repositories=(_REPO,),
        quarantine_store=QuarantineStore(os.path.join(tmp, "q.jsonl")),
    )
    store = DocumentStore(gate)
    store.add(Document(
        content=_CONTENT,
        provenance=Provenance(
            source="github", repository=_REPO, path="docs/ops.md", commit_sha="c" * 40,
            timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO, license="MIT",
        ),
    ))
    return SidraService(settings, store=store, gate=gate)


def _answer(result) -> str:
    d = result if isinstance(result, dict) else result.__dict__
    return str(d.get("answer") or "")


def _direct_body(user_message: str) -> str:
    """The echo backend's answer when only ``user_message`` is set - no
    ``retrieval_query``. A direct caller (test, other backend) that names a
    subject in the turn must still get a query-relevant body: ``_lead`` falls
    back to ``user_message`` when ``retrieval_query`` is empty (C-1827/C-1828).
    """
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    block = (
        "<<<SIDRA_DATA_BLOCK S1>>>\n"
        f"source: {_REPO}@cccccccc:docs/ops.md\n"
        "trust: retrieved-data\n"
        f"content:\n{_CONTENT}\n"
        "<<<END_SIDRA_DATA_BLOCK S1>>>"
    )
    request = GenerationRequest(
        system_prompt="", user_message=user_message, data_context=block,
    )
    return EchoModelAdapter().generate(request).text


def evaluate_answer_body_follows_carried_subject() -> AnswerBodyCarriesSubjectResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    svc = _service()
    q = "デプロイはどうやって走りますか"
    direct = svc.chat(q)
    history = [(q, _answer(direct))]
    followup = _answer(svc.chat("もっと詳しく", history=history))
    other = _answer(svc.chat("詳しく", history=history))

    # (A) baseline: the direct question's body shows the answering sentence.
    add(_ANSWER_MARK in _answer(direct),
        f"A: direct body lost the subject: {_answer(direct)[:60]!r}")
    # (B)/(C) the carried follow-up's body shows it too, not the chunk opening.
    add(_ANSWER_MARK in followup,
        f"B: 「もっと詳しく」body missing {_ANSWER_MARK!r}: {followup[:80]!r}")
    add(_ANSWER_MARK in other,
        f"C: 「詳しく」body missing {_ANSWER_MARK!r}: {other[:80]!r}")
    # (D) the follow-up body opens on the subject sentence, not the filler.
    add("デプロイは" in followup,
        f"D: 「もっと詳しく」body did not open on the subject: {followup[:80]!r}")
    # (E) a direct caller that names a subject in the turn but sets no
    # retrieval_query still gets a query-relevant body (the user_message
    # fallback). Distinguishes the fallback from a bare retrieval_query read.
    direct_only = _direct_body("デプロイの所要時間は")
    add(_ANSWER_MARK in direct_only,
        f"E: direct body without retrieval_query lost the subject: {direct_only[:80]!r}")

    total = 5
    return AnswerBodyCarriesSubjectResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "AnswerBodyCarriesSubjectResult",
    "evaluate_answer_body_follows_carried_subject",
]
