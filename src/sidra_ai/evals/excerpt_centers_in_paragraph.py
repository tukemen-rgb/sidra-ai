"""Does the citation excerpt find the answer inside a Japanese paragraph?

C-1270: ``select_excerpt_window`` (C-983) moves the excerpt window to where the
query is discussed, but its candidate window starts come only from newline
positions (``_candidate_starts``). Japanese prose ends sentences with 。 and
runs a whole paragraph on one line, so such a chunk offers a single candidate -
the head - and the window cannot move. Ask about something written past the
200-character cap inside one paragraph and the citation shows the paragraph's
opening, not the sentence that answered the question: evidence that proves
nothing, the exact failure citations exist to prevent. English Markdown escapes
it only because it carries hard line breaks.

The fix adds sentence boundaries (。！？．) to the candidate starts, so the
window can open on the answering sentence even with no newline near it. This
measures the property a reader cares about - the shown excerpt contains the
answer - through ``select_excerpt_window`` (the function the service uses to
build every citation) and once through the real chat path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_FILLER = "前置きの段落がここに続く。"
_TAIL = "その後の説明がここに続く。"

#: Single-paragraph Japanese chunks (no newlines) whose answering sentence sits
#: past the 200-character cap. Each is (content, query, answer_phrase).
_PARAGRAPH_CASES: tuple[tuple[str, str, str], ...] = (
    (
        _FILLER * 40 + "重要: バックアップは毎日午前 3 時に実行されます。" + _TAIL * 20,
        "バックアップの実行時刻はいつですか",
        "バックアップは毎日午前 3 時",
    ),
    (
        _FILLER * 45 + "認証トークンは環境変数 SIDRATOKEN に設定します。" + _TAIL * 15,
        "認証トークンはどこに設定しますか",
        "環境変数 SIDRATOKEN",
    ),
    (
        _FILLER * 50 + "障害時の連絡先は運用チームのオンコール窓口です。" + _TAIL * 10,
        "障害時の連絡先を教えてください",
        "運用チームのオンコール窓口",
    ),
)


@dataclass(frozen=True)
class ExcerptCentersResult:
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

    tmp = Path(tempfile.mkdtemp(prefix="excerpt-center-"))
    repo = "tukemen-rgb/sidra-ai"
    settings = Settings(allowed_repositories=(repo,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repo,),
        quarantine_store=QuarantineStore(tmp / "q.jsonl"),
    )
    store = DocumentStore(gate)
    prov = Provenance(
        source="github", repository=repo, path="docs/ops.md", commit_sha="d" * 40,
        timestamp=datetime(2026, 9, 3, tzinfo=timezone.utc),
        source_type=SourceType.DOCS, trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )
    store.add(Document(content=content, provenance=prov))
    service = SidraService(settings, store=store, gate=gate)
    result = service.chat(query) or {}
    citations = result.get("citations") or []
    return str(citations[0].get("excerpt")) if citations else ""


def evaluate_excerpt_centers_in_paragraph() -> ExcerptCentersResult:
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

    # 1 (per case): the window the service builds contains the answer sentence.
    for content, query, answer in _PARAGRAPH_CASES:
        window = select_excerpt_window(content, query)
        add(answer in window,
            f"paragraph {query!r}: window omits the answer 「{answer}」")
        add(len(window) <= MAX_CITATION_EXCERPT_CHARS,
            f"paragraph {query!r}: window over the cap ({len(window)})")

    # 2: end-to-end through the real chat path, the shown excerpt has the answer.
    content, query, answer = _PARAGRAPH_CASES[0]
    excerpt = _service_excerpt(content, query)
    add(answer in excerpt, f"service excerpt omits the answer 「{answer}」: {excerpt[:60]!r}")

    # 3: a chunk that already carries a newline before the answer still centres
    #    (the fix must not lose the behaviour it extends).
    nl_content = _FILLER * 40 + "\n重要: デプロイは毎週金曜の夜に行います。\n" + _TAIL * 20
    nl_window = select_excerpt_window(nl_content, "デプロイはいつ行いますか")
    add("デプロイは毎週金曜の夜" in nl_window, "newline chunk no longer centres")

    # 4: the documented fallback survives - an empty or unmatched query opens at
    #    the top, never a sentence in the middle chosen at random.
    fb_content = _PARAGRAPH_CASES[0][0]
    add(select_excerpt_window(fb_content, "") == fb_content[:MAX_CITATION_EXCERPT_CHARS],
        "empty query no longer opens at the top")
    add(select_excerpt_window(fb_content, "zzz qqq") == fb_content[:MAX_CITATION_EXCERPT_CHARS],
        "unmatched query no longer opens at the top")

    total = 2 * len(_PARAGRAPH_CASES) + 4
    return ExcerptCentersResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ExcerptCentersResult", "evaluate_excerpt_centers_in_paragraph"]
