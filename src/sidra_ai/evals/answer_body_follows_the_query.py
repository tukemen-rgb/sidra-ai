"""Does the extractive answer body show the sentence that answers the question?

C-1825. The citation excerpt a reader can open was made query-relevant
(C-1782/C-1270/C-1280: ``select_excerpt_span`` opens the window on the sentence
that carries the query's terms). But the answer body itself - the first thing the
reader sees, the ``[S#]`` block the echo backend prints - was built by ``_lead``,
which always took the chunk's *opening* sentences regardless of the question. So a
chunk whose answering sentence sits past the opening answered "What is the default
port?" with its first two sentences about the language and dependencies, and the
sentence "The default port is 8080" showed only in the citation excerpt below -
the answer box did not answer the question, though the evidence was retrieved and
on screen. ``_lead`` now opens the answer on the sentence whose terms best match
the query (falling back to the opening when nothing matches or the query is
empty, so ordinary answers are unchanged), the same relevance the citation
excerpt already had.

Measured through the real ``SidraService.chat`` with the echo backend, over both
languages, and both directions: the answering sentence appears for a question it
answers, and a question about the opening still shows the opening (and does not
drag in a later sentence).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone


_EN = (
    "The service is written in Python and packaged as a wheel. "
    "It depends on FastAPI and uvicorn for serving. "
    "The default port is 8080 unless overridden. "
    "Logging goes to stdout in JSON."
)
_JP = (
    "このサービスはPythonで書かれています。"
    "FastAPIとuvicornに依存します。"
    "デフォルトのポートは8080です。"
    "ログはJSONで標準出力に出ます。"
)

#: (content, query, needle-that-must-appear-in-the-answer-body). The answering
#: sentence sits past the opening in every "fix" row.
_PRESENT = (
    (_EN, "What is the default port?", "8080"),
    (_EN, "What is the default port?", "default port"),
    (_JP, "デフォルトのポートは何番ですか", "8080"),
    # Controls: a question about the opening still shows the opening.
    (_EN, "What language is the service written in?", "Python"),
    (_JP, "このサービスは何で書かれていますか", "Python"),
)

#: (content, query, needle-that-must-NOT-appear). The opening-question answer must
#: not over-reach and drag in the later port sentence.
_ABSENT = (
    (_EN, "What language is the service written in?", "8080"),
)


@dataclass(frozen=True)
class AnswerBodyFollowsQueryResult:
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
        source="github", repository=repo, path="docs/run.md", commit_sha="abc1234",
        timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
    )
    store.add(Document(content=content, provenance=prov))
    service = SidraService(
        Settings(data_dir=tempfile.mkdtemp()),
        model=EchoModelAdapter(), store=store, gate=gate,
    )
    return str((service.chat(query) or {}).get("answer") or "")


def evaluate_answer_body_follows_the_query() -> AnswerBodyFollowsQueryResult:
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
            f"{query!r}: answer body over-reached and included {needle!r}: 「{answer}」")

    total = len(_PRESENT) + len(_ABSENT)
    return AnswerBodyFollowsQueryResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "AnswerBodyFollowsQueryResult",
    "evaluate_answer_body_follows_the_query",
]
