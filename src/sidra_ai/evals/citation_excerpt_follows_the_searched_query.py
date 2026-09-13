"""Does a follow-up's citation excerpt show the passage under discussion?

C-1782. When a follow-up has no content subject of its own (「もっと詳しく」),
``chat`` carries the previous question and retrieves on ``searched_query``, but
attached the excerpt window with the bare ``query``. ``select_excerpt_window``
scores windows by the query's terms; a subjectless follow-up scores every window
zero and falls back to the chunk opening - so the excerpt shown under 出典 was
the top of the document, not the passage that grounds the answer, defeating the
one thing the excerpt exists for. The excerpt is now selected with
``searched_query`` (which equals ``query`` on a single turn, so ordinary
excerpts are unchanged).

The checks drive the real ``SidraService.chat`` with the echo backend over a
chunk whose subject sentence sits past the excerpt cap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sidra_ai.api.citations import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

_REPO = "tukemen-rgb/site"
_SUBJECT = "デプロイ"
#: Opening filler longer than the excerpt cap, so the subject sentence that
#: follows it cannot land in the fallback (opening) window.
_FILLER = "この文書は運用全般の背景を説明します。歴史的な経緯や関係者の話が続きます。" * 10
_SUBJECT_SENTENCE = "デプロイはmainへのpushで自動的に走り、所要時間はおよそ5分です。失敗時は自動でロールバックされます。"
_CONTENT = _FILLER + _SUBJECT_SENTENCE + "その後の注意事項がさらに続きます。" * 3


def _service() -> SidraService:
    # Through the shared helper, not tempfile directly (C-1770): a judge
    # that makes its own scratch and never removes it is what filled this
    # container's disk. scratch_dir registers the directory for removal at
    # interpreter exit.
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


def _excerpt(result) -> str:
    d = result if isinstance(result, dict) else result.__dict__
    cites = d.get("citations") or []
    return (cites[0].get("excerpt") or "") if cites else ""


def _ncites(result) -> int:
    d = result if isinstance(result, dict) else result.__dict__
    return len(d.get("citations") or [])


@dataclass(frozen=True)
class ExcerptFollowsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_citation_excerpt_follows_the_searched_query() -> ExcerptFollowsResult:
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
    direct_ex = _excerpt(direct)
    history = [(q, (direct if isinstance(direct, dict) else direct.__dict__).get("answer", ""))]

    followup = svc.chat("もっと詳しく", history=history)
    fu_ex = _excerpt(followup)

    other = svc.chat("詳しく", history=history)
    other_ex = _excerpt(other)

    opening = _CONTENT[:MAX_CITATION_EXCERPT_CHARS]

    # --- (A) the direct question's excerpt shows the subject (baseline) ---
    add(_SUBJECT in direct_ex, f"A: the direct excerpt lost the subject: {direct_ex[:40]!r}")
    # --- (B) the follow-up's excerpt shows the subject under discussion ---
    add(_SUBJECT in fu_ex, f"B: the follow-up excerpt does not show the subject: {fu_ex[:40]!r}")
    # --- (C) ...and does not open on the filler head (the fallback) ------
    #         (a trailing 「…」 clip alone would make it != content[:200] even
    #         when it is the opening, so test the head, not string inequality.)
    add(_SUBJECT not in opening and not fu_ex.lstrip("…").startswith(_FILLER[:12]),
        f"C: the follow-up excerpt opens on the document head: {fu_ex[:40]!r}")
    # --- (D) another elaboration phrasing behaves the same --------------
    add(_SUBJECT in other_ex, f"D: 「詳しく」 excerpt does not show the subject: {other_ex[:40]!r}")
    # --- (E) the single-turn excerpt is the subject window, not the top --
    add(direct_ex != opening and _SUBJECT in direct_ex,
        f"E: the single-turn excerpt regressed to the opening: {direct_ex[:40]!r}")
    # --- (F) a first-message elaboration (no history) abstains ----------
    add(_ncites(_service().chat("もっと詳しく")) == 0,
        "F: a no-history elaboration wrongly returned citations")

    total = 6
    return ExcerptFollowsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ExcerptFollowsResult",
    "evaluate_citation_excerpt_follows_the_searched_query",
]
