"""Does the citation excerpt reach an answer written at a paragraph's tail?

C-1475, the tail twin of C-1270 (Japanese paragraph centering) and C-1280
(English). ``select_excerpt_window`` moves the excerpt window to where the query
is discussed, but ``_candidate_starts`` dropped every start closer to the end
than ``MAX_CITATION_EXCERPT_CHARS`` (``last_useful_start``), for fear that a
short tail window would score lower "for having less text, not for being less
relevant." Scoring counts *distinct* matched query terms, though, so a short
window that holds the whole answering sentence never scores below an earlier
window that clips it. The break only created a blind spot: when the answering
sentence sits in a chunk's final ~200 characters - where conclusions, values
and 「…に設定されている」 summaries usually sit - no candidate window could open on
it, and the excerpt opened on the previous boundary and cut the answer at the
far edge. That is the exact "first half of the line that answered them" failure
the window's tie-break exists to prevent, left un-prevented in the tail.

The fix lets ``_candidate_starts`` offer the tail's sentence boundaries too, so
the window can open on the answering sentence even when it is the last one.

The checks read ``select_excerpt_window`` directly and once through the real
chat path, and pin that the earlier centering (C-1270) and the top fallback are
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: A long single run-on lead (one 。, at its end) that spans more than the cap,
#: so the last candidate boundary before ``last_useful_start`` sits at the head
#: and the window opened there ends before the final sentence. The answering
#: sentence that follows is inside the chunk's last MAX_CITATION_EXCERPT_CHARS,
#: which the dropped-tail-starts bug could not open on.
_LEAD = (
    "この項目の詳細を説明すると、まず前提となる背景を丁寧に踏まえた上で、"
    "運用上の注意点をいくつも順に列挙しながら整理していく必要があり、"
    "その具体的な手順や設定の勘所についてはこの段落の中で続けて一つずつ詳しく述べていくのだが、"
    "読み手が途中で迷わないよう、あえて文の切れ目をほとんど作らず、"
    "関連する事項をまとめて一つづきの長い一文として最後まで書き切るように構成している。"
)

#: Single-paragraph Japanese chunks (no newlines) whose answering sentence is the
#: *last* one, sitting inside the final MAX_CITATION_EXCERPT_CHARS of the chunk.
#: Each is (content, query, answer_phrase).
_TAIL_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "概要。" + _LEAD + "API のレート制限は 1 分あたり 100 リクエストに設定されている。",
        "レート制限はいくつですか",
        "100 リクエスト",
    ),
    (
        "概要。" + _LEAD + "サポートの受付時間は平日の午前 9 時から午後 6 時までです。",
        "サポートの受付時間はいつですか",
        "午前 9 時から午後 6 時",
    ),
    (
        "概要。" + _LEAD + "無料枠の上限は 1 か月あたり 5000 件までと定められている。",
        "無料枠の上限はいくつですか",
        "5000 件",
    ),
)


@dataclass(frozen=True)
class ExcerptReachesTailResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service_excerpt(content: str, query: str) -> str:
    """The excerpt the real chat path would show for a one-chunk corpus."""
    import tempfile
    from datetime import datetime, timezone

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(tempfile.mkdtemp(prefix="excerpt-tail-"))
    repo = "tukemen-rgb/sidra-ai"
    settings = Settings(allowed_repositories=(repo,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repo,),
        quarantine_store=QuarantineStore(tmp / "q.jsonl"),
    )
    store = DocumentStore(gate)
    prov = Provenance(
        source="github", repository=repo, path="docs/ops.md", commit_sha="e" * 40,
        timestamp=datetime(2026, 9, 7, tzinfo=timezone.utc),
        source_type=SourceType.DOCS, trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )
    store.add(Document(content=content, provenance=prov))
    service = SidraService(settings, store=store, gate=gate)
    result = service.chat(query) or {}
    citations = result.get("citations") or []
    return str(citations[0].get("excerpt")) if citations else ""


def evaluate_excerpt_reaches_paragraph_tail() -> ExcerptReachesTailResult:
    from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
    from sidra_ai.api.citations import select_excerpt_window

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1 (per case): the window contains the tail answer, and stays within the cap.
    for content, query, answer in _TAIL_CASES:
        window = select_excerpt_window(content, query)
        add(answer in window,
            f"tail {query!r}: window omits the answer 「{answer}」 (got …{window[-24:]!r})")
        add(len(window) <= MAX_CITATION_EXCERPT_CHARS,
            f"tail {query!r}: window over the cap ({len(window)})")

    # 2: end-to-end through the real chat path, the shown excerpt has the answer.
    content, query, answer = _TAIL_CASES[0]
    excerpt = _service_excerpt(content, query)
    add(answer in excerpt, f"service excerpt omits the tail answer 「{answer}」: {excerpt[:60]!r}")

    # 3: C-1270 centering (answer mid-paragraph, with tail after) still works -
    #    the fix must extend the candidate starts, not lose the earlier ones.
    mid = "前置きの段落がここに続く。" * 40 + "重要: バックアップは毎日午前 3 時に実行されます。" + "その後の説明がここに続く。" * 20
    mid_window = select_excerpt_window(mid, "バックアップの実行時刻はいつですか")
    add("バックアップは毎日午前 3 時" in mid_window, "mid-paragraph centring (C-1270) regressed")

    # 4: the documented fallback survives - an empty or unmatched query opens at
    #    the top, never a tail sentence chosen at random.
    fb = _TAIL_CASES[0][0]
    add(select_excerpt_window(fb, "") == fb[:MAX_CITATION_EXCERPT_CHARS],
        "empty query no longer opens at the top")
    add(select_excerpt_window(fb, "zzz qqq") == fb[:MAX_CITATION_EXCERPT_CHARS],
        "unmatched query no longer opens at the top")

    total = 2 * len(_TAIL_CASES) + 4
    return ExcerptReachesTailResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ExcerptReachesTailResult", "evaluate_excerpt_reaches_paragraph_tail"]
