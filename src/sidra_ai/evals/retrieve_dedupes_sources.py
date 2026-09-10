"""Does /v1/retrieve return distinct sources, in descending score order?

C-1646. ``/v1/retrieve`` is source discovery: its docstring omits chunk
content and returns "provenance and ranking only", so every citation comes
back with ``excerpt=""``. But the shared retriever diversifies breadth-first
and then backfills extra chunks from the same document to fill ``top_k``. For
chat those depth chunks each carry their own excerpt and are useful; for
retrieve, with excerpts omitted, they collapse to citations identical in
everything a caller can see - same ``repo@sha:path``, empty excerpt, differing
only by score. The result was the same source listed several times and a score
column that was not monotonic (a lower-scored distinct source outranking a
higher-scored backfill chunk), padding a discovery list with repeats.

The checks build a store with one multi-chunk document and a couple of small
ones, then a wider set of distinct documents, and assert retrieve returns each
source once, in non-increasing score order, without dropping distinct sources
when enough exist - while the honest no-evidence path is untouched.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone

_REPO = "tukemen-rgb/site"


def _service(documents):
    """documents: list of (path, content). Returns a SidraService over them."""
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import SecurityGate

    gate = SecurityGate()
    store = DocumentStore(gate)
    for path, content in documents:
        provenance = Provenance(
            source="github",
            repository=_REPO,
            path=path,
            commit_sha="abc1234",
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="proprietary",
        )
        result = gate.inspect(content, source="github", repository=_REPO)
        store.add(Document(content=content, provenance=provenance), gate_result=result)
    settings = Settings(data_dir=tempfile.mkdtemp())
    return SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)


def _paths(response):
    return [r["citation"]["path"] for r in response["results"]]


def _descending(scores):
    return all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))


@dataclass(frozen=True)
class RetrieveDedupeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_retrieve_dedupes_sources() -> RetrieveDedupeResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- narrow corpus: one big multi-chunk doc + two small ones ---
    paragraph = (
        "The alpha widget subsystem coordinates the beta gamma pipeline and delta "
        "epsilon routing so the alpha widget stays consistent across the beta gamma "
        "boundary in every alpha widget run. "
    ) * 3
    big = "\n\n".join(f"Section {i}: {paragraph}" for i in range(6))
    narrow = _service([
        ("big.md", big),
        ("small_b.md", "The alpha widget note in small b mentions the alpha widget here."),
        ("small_c.md", "The alpha widget note in small c mentions the alpha widget there."),
    ])
    resp = narrow.retrieve("alpha widget", top_k=6)
    paths = _paths(resp)
    scores = [r["score"] for r in resp["results"]]
    add(len(paths) == len(set(paths)),
        f"narrow: duplicate sources in results: {paths}")
    add(_descending(scores), f"narrow: scores not descending: {scores}")
    add(set(paths) == {"big.md", "small_b.md", "small_c.md"},
        f"narrow: lost a distinct source: {sorted(set(paths))}")
    add(len(paths) == 3, f"narrow: expected 3 distinct sources, got {len(paths)}")
    add(resp["refused"] is False and resp["reason"] == "",
        f"narrow: refused/reason wrong: {resp['refused']} {resp['reason']!r}")

    # --- wide corpus: enough distinct sources to fill top_k (no over-dedupe) ---
    wide = _service([
        (f"doc_{i}.md", f"Document {i} about the alpha widget and its alpha widget behavior.")
        for i in range(6)
    ])
    wresp = wide.retrieve("alpha widget", top_k=5)
    wpaths = _paths(wresp)
    wscores = [r["score"] for r in wresp["results"]]
    add(len(wpaths) == 5, f"wide: expected 5 results, got {len(wpaths)}")
    add(len(wpaths) == len(set(wpaths)), f"wide: duplicate sources: {wpaths}")
    add(_descending(wscores), f"wide: scores not descending: {wscores}")

    # --- honest no-evidence path is untouched ---
    nresp = narrow.retrieve("zzzznonexistenttopicphrase", top_k=5)
    add(nresp["results"] == [], f"nonsense: expected no results, got {len(nresp['results'])}")
    add(nresp["reason"] == "no indexed evidence matched the query",
        f"nonsense: reason changed: {nresp['reason']!r}")

    # --- response shape unchanged ---
    add(resp["model_invoked"] is False and isinstance(resp["security"], dict) and resp["security"],
        "narrow: model_invoked/security shape changed")

    total = 11
    return RetrieveDedupeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["RetrieveDedupeResult", "evaluate_retrieve_dedupes_sources"]
