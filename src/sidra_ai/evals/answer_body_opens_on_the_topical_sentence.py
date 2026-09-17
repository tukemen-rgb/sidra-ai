"""Does the answer body open on the topical sentence, or one that shares a
low-value word?

C-1911. ``_lead`` opens the extractive answer on the sentence whose tokens
best overlap the query (C-1827). The overlap was an exact-token match, so two
things could hand the opening to the wrong sentence at once:

  * a low-information word the question phrasing carries ("done" in "How are
    deployments **done**?") matches a distractor sentence ("Rollbacks are
    **done** with kubectl rollout undo"), and
  * the one salient content word misses its own sentence over a trivial plural
    ("deployment**s**" in the query never matches "**Deployment** uses GitHub
    Actions").

So "How are deployments done?" answered with the rollback command instead of
the deployment description - the citation excerpt below carried the whole
document and was right, but the answer box, the first thing the reader sees,
was a confident wrong answer. That is worse than an honest "no evidence".

The fix folds a trailing plural ``s`` on both sides of the overlap for the
sentence-opening score only (retrieval, measured separately, is untouched), so
"deployments" matches "deployment". The salient word then ties the low-value
one, and the tie keeps the earlier - here topical - sentence. Measured through
the real ``SidraService.chat`` with the echo backend, with controls that keep a
genuinely later sentence winning when it is the real answer, and that keep the
singular phrasing working.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sidra_ai.evals.scratch import scratch_dir


_DEPLOY = (
    "Deployment uses GitHub Actions. "
    "The pipeline runs tests, builds a Docker image, and pushes to the registry. "
    "Rollbacks are done with kubectl rollout undo."
)
_RELEASE = (
    "A release follows semantic versioning. "
    "The version number is bumped in the changelog. "
    "Announcements are made on the blog."
)
#: The reverse direction: the topical word is PLURAL in the corpus and SINGULAR
#: in the query. This is why the fold is applied to the sentence side too, not
#: only the query - a one-sided fold would leave "snapshots" unmatched by
#: "snapshot" and hand the opening to the "done" distractor.
_SNAPSHOT = (
    "The snapshots are kept for thirty days. "
    "Old ones are pruned from cold storage. "
    "Cleanup is done nightly."
)

#: (content, query, needle-that-must-appear-in-the-answer-body).
_PRESENT = (
    # The defect: the plural query must reach the deployment sentence, not the
    # rollback sentence that only shares the low-value word "done".
    (_DEPLOY, "How are deployments done?", "GitHub Actions"),
    # A second, independent plural-vs-singular case: "releases" -> "release",
    # where the distractor ("Announcements are made") shares only "made".
    (_RELEASE, "How are releases made?", "semantic versioning"),
    # Reverse direction: singular query "snapshot" must reach the plural corpus
    # word "snapshots"; the distractor ("Cleanup is done nightly") shares "done".
    # Requires folding the sentence side too, not only the query.
    (_SNAPSHOT, "How is a snapshot done?", "thirty days"),
    # Control - singular phrasing already worked and must keep working.
    (_DEPLOY, "How is deployment done?", "GitHub Actions"),
    # Control - a genuinely later sentence must still win when it is the real
    # answer, so the fix is not "always open on sentence one".
    (_DEPLOY, "What registry are images pushed to?", "registry"),
)

#: (content, query, needle-that-must-NOT-appear-in-the-answer-body).
_ABSENT = (
    (_DEPLOY, "How are deployments done?", "rollout undo"),
    (_RELEASE, "How are releases made?", "blog"),
    (_SNAPSHOT, "How is a snapshot done?", "nightly"),
)


@dataclass(frozen=True)
class AnswerBodyOpensOnTopicalSentenceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _answer_of(content: str, query: str) -> str:
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    repo = "acme/app"
    gate = SecurityGate(GatePolicy(), allowed_repositories=(repo,))
    store = DocumentStore(gate)
    prov = Provenance(
        source="github", repository=repo, path="docs/ops.md", commit_sha="abc1234",
        timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
    )
    store.add(Document(content=content, provenance=prov))
    service = SidraService(
        Settings(data_dir=scratch_dir()),
        model=EchoModelAdapter(), store=store, gate=gate,
    )
    return str((service.chat(query) or {}).get("answer") or "")


def evaluate_answer_body_opens_on_the_topical_sentence() -> (
    AnswerBodyOpensOnTopicalSentenceResult
):
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for content, query, needle in _PRESENT:
        answer = _answer_of(content, query)
        add(needle in answer,
            f"{query!r}: answer body missing {needle!r}: 「{answer}」")

    for content, query, needle in _ABSENT:
        answer = _answer_of(content, query)
        add(needle not in answer,
            f"{query!r}: answer body opened on the wrong sentence, "
            f"included {needle!r}: 「{answer}」")

    total = len(_PRESENT) + len(_ABSENT)
    return AnswerBodyOpensOnTopicalSentenceResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "AnswerBodyOpensOnTopicalSentenceResult",
    "evaluate_answer_body_opens_on_the_topical_sentence",
]
