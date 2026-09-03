"""Does chat say "no evidence" when the corpus knows nothing about the subject?

C-1201: BM25's CJK bigrams fill ``top_k`` on cross-word glue (「を教」 out of
「天気を教えて」), so a question about the weather came back as five cited
excerpts about marketing copy, ``refused: false``. The floor being measured
here is :func:`sidra_ai.retrieval.search.evidence_mentions_subject` applied
the way the chat path applies it: retrieve first, then require at least one
retrieved chunk to share a subject term with the question before an answer
may be composed.

Two failure directions are scored, because the floor can be wrong both ways:

* An **off-topic** probe passes when the pipeline ends with no usable
  evidence (retrieval empty, or every chunk gated as glue-only).
* An **on-topic** probe passes when the gate keeps the evidence - a floor
  that silences answerable questions is a worse product than the one that
  bluffed.

The corpus is synthetic and deliberately glue-rich: every off-topic probe
below retrieves non-empty results from it via bigram glue, which is the shape
of the real failure. A probe that retrieved nothing would pass with or
without the gate and would prove nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from sidra_ai.documents import Chunk, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.search import BM25Retriever


@dataclass(frozen=True)
class HonestyProbe:
    name: str
    query: str
    #: True when the corpus genuinely contains the subject and the answer
    #: path must keep its evidence; False when honesty demands "not found".
    answerable: bool


@dataclass(frozen=True)
class QaHonestyResult:
    passed: bool
    #: Off-topic probes that ended with no usable evidence.
    refused_offtopic: int
    offtopic_total: int
    #: On-topic probes whose evidence survived the gate.
    kept_ontopic: int
    ontopic_total: int
    failures: tuple[str, ...] = ()


class _EvalStore:
    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = tuple(chunks)

    def chunks(self) -> tuple[Chunk, ...]:
        return self._chunks


def _chunk(content: str, *, path: str, index: int) -> Chunk:
    provenance = Provenance(
        source="github",
        repository="tukemen-rgb/sidra-ai",
        path=path,
        commit_sha="e" * 40,
        timestamp=datetime(2026, 9, 3, tzinfo=timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )
    return Chunk(
        content=content,
        provenance=provenance,
        document_id=f"qa-honesty-{index}",
        index=0,
    )


#: Glue-rich on purpose: 「〜を教えてください」「〜はどうなっていますか」 and
#: friends make the off-topic probes below retrieve real results, the way the
#: 484-document corpus did for 「天気を教えて」.
_EVAL_CHUNKS: tuple[Chunk, ...] = (
    _chunk(
        "広告の方針を教えてください、と聞かれたら第三者 JS を載せない方針を"
        "案内する。掲載の判断は安全性を壊さないことが条件になっています。",
        path="docs/ads.md", index=0,
    ),
    _chunk(
        "運営コストはどうなっていますか。ビルド成果物を実測した値だけを"
        "資料に載せる。古い数字を出さないことを教えてもらうまでもなく守る。",
        path="docs/cost.md", index=1,
    ),
    _chunk(
        "キャッチコピーの案はここにまとめています。つくる人を育てることを"
        "軸に、次の掲載に向けて案を並べて選びます。",
        path="docs/brand.md", index=2,
    ),
    _chunk(
        "セキュリティの方針: 外部コンテンツは DATA として扱い、命令として"
        "実行しない。秘密情報を索引へ入れないことになっています。",
        path="docs/security.md", index=3,
    ),
    _chunk(
        "The ingestion client is read-only and permits GET requests only. "
        "Write operations are refused before any network call is made.",
        path="docs/readonly.md", index=4,
    ),
)


PROBES: tuple[HonestyProbe, ...] = (
    # The reproduction from the C-1201 report, and its neighbours: subjects
    # the corpus has never heard of, phrased with everyday glue.
    HonestyProbe("weather", "天気を教えて", answerable=False),
    HonestyProbe("weather-tomorrow", "明日の天気を教えてください", answerable=False),
    HonestyProbe("phone-number", "電話番号を教えてください", answerable=False),
    HonestyProbe("paid-leave", "有給休暇の申請を教えてください", answerable=False),
    HonestyProbe("stock-price", "株価を教えて", answerable=False),
    # Subjects the corpus does contain; the floor must not eat them.
    HonestyProbe("ads-policy", "広告の方針を教えて", answerable=True),
    HonestyProbe("cost", "運営コストはいくらですか", answerable=True),
    HonestyProbe("copy-ideas", "キャッチコピーの案を教えて", answerable=True),
    HonestyProbe("security-policy", "セキュリティの方針を教えてください", answerable=True),
    HonestyProbe("readonly", "Is the ingestion client read-only?", answerable=True),
)


@dataclass(frozen=True)
class ErrorLanguageResult:
    """C-1202: the no-evidence reply must speak the question's language."""

    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_no_evidence_language() -> ErrorLanguageResult:
    """Ask an empty-corpus service in both languages; judge the canned reply.

    Four checks, all through the real ``chat`` path: the Japanese question
    gets a Japanese abstention (no English boilerplate), the English question
    keeps the English one, and both replies still register as honest
    abstention with :func:`sidra_ai.evals.grounding.evaluate_grounding` -
    a translated message that stops counting as abstention would trade a
    wording bug for a measurement bug.
    """

    from sidra_ai.evals.grounding import evaluate_grounding

    service = _build_service(populate=False)
    checks = 0
    failures: list[str] = []

    japanese = service.chat("天気を教えて")
    if "No indexed evidence" not in japanese["answer"] and "根拠がありません" in japanese["answer"]:
        checks += 1
    else:
        failures.append("japanese question answered with the English canned text")
    if evaluate_grounding(japanese["answer"], japanese["citations"]).passed:
        checks += 1
    else:
        failures.append("japanese abstention no longer counts as abstention")

    english = service.chat("What changed recently?")
    if "No indexed evidence" in english["answer"]:
        checks += 1
    else:
        failures.append("english question lost the English canned text")
    if evaluate_grounding(english["answer"], english["citations"]).passed:
        checks += 1
    else:
        failures.append("english abstention no longer counts as abstention")

    return ErrorLanguageResult(
        passed=not failures, checks_passed=checks, checks_total=4,
        failures=tuple(failures),
    )


def _build_service(populate: bool = True):
    """A real ``SidraService`` over the synthetic corpus, echo backend.

    The probes run through ``chat`` itself rather than re-implementing its
    retrieval-then-gate sequence, so that removing the gate from the service
    - the most likely way this fix regresses - drops this number to 0 instead
    of leaving a green instrument pointed at code nobody runs.
    """

    import tempfile
    from pathlib import Path

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(tempfile.mkdtemp(prefix="qa-honesty-"))
    repository = "tukemen-rgb/sidra-ai"
    settings = Settings(
        allowed_repositories=(repository,), data_dir=str(tmp / "sidra")
    )
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repository,),
        quarantine_store=QuarantineStore(tmp / "quarantine.jsonl"),
    )
    store = DocumentStore(gate)
    if populate:
        for chunk in _EVAL_CHUNKS:
            store.add(Document(content=chunk.content, provenance=chunk.provenance))
    return SidraService(settings, store=store, gate=gate)


def evaluate_qa_honesty() -> QaHonestyResult:
    retriever = BM25Retriever(_EvalStore(_EVAL_CHUNKS))
    service = _build_service()
    refused = kept = offtopic = ontopic = 0
    failures: list[str] = []

    for probe in PROBES:
        # The gate must have something to gate: an off-topic probe that no
        # longer retrieves anything exercises nothing and is a broken probe,
        # not a pass. Checked against the retriever directly because chat
        # does not report what retrieval returned before composition.
        retrieved = retriever.search(probe.query, top_k=5)

        result = service.chat(probe.query)
        answered = bool(result.get("citations")) and not result.get("refused")

        if probe.answerable:
            ontopic += 1
            if answered:
                kept += 1
            else:
                failures.append(f"{probe.name}: on-topic evidence was gated away")
        else:
            offtopic += 1
            if not retrieved:
                failures.append(f"{probe.name}: probe retrieved nothing, proves nothing")
            elif not answered:
                refused += 1
            else:
                failures.append(f"{probe.name}: glue-only evidence was answered")

    return QaHonestyResult(
        passed=not failures,
        refused_offtopic=refused,
        offtopic_total=offtopic,
        kept_ontopic=kept,
        ontopic_total=ontopic,
        failures=tuple(failures),
    )
