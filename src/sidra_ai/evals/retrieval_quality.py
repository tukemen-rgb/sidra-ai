"""Offline retrieval-quality regressions for the v0.1 RAG path.

Citation integrity is necessary but not sufficient: a model can cite a real
``[S1]`` label while retrieval selected the wrong source.  These checks keep a
small multilingual benchmark around the current BM25/CJK-bigram retriever so
that evidence selection regressions fail before a local model is involved.

The corpus and queries are synthetic, contain no secrets/PII, require no
network access or model weights, and deliberately include distractors that
share terms with the expected source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from sidra_ai.documents import Chunk, Provenance, SourceType, TrustLevel
from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.retrieval.search import BM25Retriever


@dataclass(frozen=True)
class RetrievalCase:
    """One deterministic evidence-selection expectation."""

    name: str
    query: str
    expected_path: str | None
    max_rank: int = 1


@dataclass(frozen=True)
class RetrievalQualityResult:
    """Aggregate retrieval metrics for a case set."""

    passed: bool
    mean_reciprocal_rank: float
    recall_at_3: float
    failures: tuple[str, ...] = ()


class _EvalStore:
    """Minimal read-only store interface required by :class:`BM25Retriever`."""

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = tuple(chunks)

    def chunks(self) -> tuple[Chunk, ...]:
        return self._chunks


def _chunk(content: str, *, path: str, index: int) -> Chunk:
    provenance = Provenance(
        source="eval",
        repository="tukemen-rgb/sidra-ai",
        path=path,
        commit_sha="d" * 40,
        timestamp=datetime(2026, 8, 15, tzinfo=timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )
    return Chunk(
        content=content,
        provenance=provenance,
        document_id=f"retrieval-eval-{index}",
        index=0,
    )


_EVAL_CHUNKS: tuple[Chunk, ...] = (
    _chunk(
        "GitHub ingestion is read-only. The client permits GET requests only and "
        "exposes no write, deploy, mutation, POST, PATCH, PUT, or DELETE capability.",
        path="docs/READ_ONLY.md",
        index=0,
    ),
    _chunk(
        "SIDRA AI runs local language models and does not require a paid external "
        "LLM API. Ollama, llama.cpp, and Transformers are replaceable local backends.",
        path="docs/LOCAL_MODEL.md",
        index=1,
    ),
    _chunk(
        "The private API binds to localhost 127.0.0.1 by default. Public network "
        "binding is disabled unless explicit safeguards are configured.",
        path="docs/API.md",
        index=2,
    ),
    _chunk(
        "差分取得では最後に成功したcommit SHAを保存し、変更がない場合は再取得とLLM推論を"
        "スキップする。GitHub compareで変更だけを処理する。",
        path="docs/INGESTION.md",
        index=3,
    ),
    _chunk(
        "外部コンテンツとGitHubのIssueやPR本文はDATAとして扱い、命令として実行しない。"
        "Prompt Injectionを検知し、秘密情報と個人情報を索引へ入れない。",
        path="docs/SECURITY.md",
        index=4,
    ),
    _chunk(
        "Product ideas are compared on user value, revenue, feasibility, and "
        "differentiation. This document contains no runtime or retrieval policy.",
        path="docs/BUSINESS.md",
        index=5,
    ),
)


RETRIEVAL_CASES: tuple[RetrievalCase, ...] = (
    RetrievalCase(
        name="retrieval_read_only_english",
        query="GitHub write operation is forbidden and access must stay read only",
        expected_path="docs/READ_ONLY.md",
    ),
    RetrievalCase(
        name="retrieval_local_model_japanese",
        query="外部有料LLM APIを使わずローカルモデルで推論する",
        expected_path="docs/LOCAL_MODEL.md",
    ),
    RetrievalCase(
        name="retrieval_loopback_mixed",
        query="APIはlocalhost 127.0.0.1だけで待ち受ける",
        expected_path="docs/API.md",
    ),
    RetrievalCase(
        name="retrieval_commit_diff_japanese",
        query="変更がないときcommit SHAで差分取得をスキップする",
        expected_path="docs/INGESTION.md",
    ),
    RetrievalCase(
        name="retrieval_data_not_instructions_mixed",
        query="Prompt InjectionをDATAとして扱い秘密情報を索引に入れない",
        expected_path="docs/SECURITY.md",
    ),
    RetrievalCase(
        name="retrieval_no_evidence_abstention_input",
        query="今日の確定売上と入金額はいくらか",
        expected_path=None,
    ),
)


def evaluate_retrieval_quality(
    cases: Sequence[RetrievalCase] = RETRIEVAL_CASES,
) -> RetrievalQualityResult:
    """Measure MRR/Recall@3 and enforce the rank expectations in ``cases``."""

    retriever = BM25Retriever(_EvalStore(_EVAL_CHUNKS))  # type: ignore[arg-type]
    failures: list[str] = []
    reciprocal_ranks: list[float] = []
    recall_hits = 0
    evidence_cases = 0

    for case in cases:
        results = retriever.search(case.query, top_k=3)
        paths = [result.provenance.path for result in results]

        if case.expected_path is None:
            if results:
                failures.append(
                    f"{case.name}: expected no evidence, got {paths!r}"
                )
            continue

        evidence_cases += 1
        try:
            rank = paths.index(case.expected_path) + 1
        except ValueError:
            rank = 0

        if rank:
            reciprocal_ranks.append(1.0 / rank)
            recall_hits += 1
        else:
            reciprocal_ranks.append(0.0)

        if rank == 0:
            failures.append(
                f"{case.name}: expected {case.expected_path} in top-3, got {paths!r}"
            )
        elif rank > case.max_rank:
            failures.append(
                f"{case.name}: expected rank <= {case.max_rank}, got rank {rank}"
            )

    mrr = sum(reciprocal_ranks) / evidence_cases if evidence_cases else 1.0
    recall_at_3 = recall_hits / evidence_cases if evidence_cases else 1.0

    if mrr < 1.0:
        failures.append(f"retrieval MRR regressed below 1.0: {mrr:.3f}")
    if recall_at_3 < 1.0:
        failures.append(f"retrieval recall@3 regressed below 1.0: {recall_at_3:.3f}")

    return RetrievalQualityResult(
        passed=not failures,
        mean_reciprocal_rank=mrr,
        recall_at_3=recall_at_3,
        failures=tuple(failures),
    )


def run_retrieval_quality_suite() -> tuple[EvalOutcome, ...]:
    """Expose retrieval quality through the standard offline eval runner."""

    result = evaluate_retrieval_quality()
    return (
        EvalOutcome(
            case_name="rag_retrieval_relevance_multilingual",
            passed=result.passed,
            detail=(
                f"mrr={result.mean_reciprocal_rank:.3f}; "
                f"recall@3={result.recall_at_3:.3f}; cases={len(RETRIEVAL_CASES)}"
            ),
            failures=result.failures,
        ),
    )
