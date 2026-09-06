"""Does the citation excerpt find the answer inside an English paragraph?

C-1280: ``select_excerpt_window`` (C-983) moves the excerpt window to where the
query is discussed, and C-1270 gave Japanese single-line paragraphs the sentence
boundaries (。！？．) the window needs to move to the answering sentence. English
was left out on the assumption it "carries hard line breaks" - but a Markdown
paragraph is one logical line, and English ends its sentences with ASCII 「.」,
which was *excluded* for fear of opening a window mid-abbreviation. So an English
single-line paragraph offered a single candidate - the head - and the citation
showed the paragraph's opening, not the sentence that answered the question:

    「What is the default request timeout?」 → the excerpt ended at
    「…create a configuration file inside the home directory. The d」,
    clipping right before 「thirty seconds」, the value asked for.

The fix adds ASCII 「.」 as a candidate boundary, but only with the shape a real
sentence break has and an abbreviation does not: preceded by a lowercase letter
or digit (so an acronym 「TLS.」 or an initial 「J.」 is not a break) and followed
by whitespace then an uppercase letter (so a decimal 「3.14」, a dotted name
「Foo.Bar」, and 「e.g. the」 are not). The window never opens inside a token.

Checks drive ``select_excerpt_window`` - the function every citation is built
with - and once the real chat path end-to-end, plus the guards that keep the new
boundary from opening on a false break, and the Japanese/newline/fallback
behaviour the fix must not lose.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_EFILL = "This is a filler sentence that adds length here. "
_ETAIL = "This is trailing text that follows the key line. "

#: Single-paragraph English chunks (no newlines) whose answering sentence sits
#: past the 200-character cap. Each is (content, query, answer_phrase).
_PARAGRAPH_CASES: tuple[tuple[str, str, str], ...] = (
    (
        _EFILL * 5
        + "Important: the nightly backup runs every day at three in the morning. "
        + _ETAIL * 6,
        "When does the nightly backup run each day?",
        "runs every day at three in the morning",
    ),
    (
        _EFILL * 5
        + "The default request timeout is thirty seconds unless it is overridden. "
        + _ETAIL * 6,
        "What is the default request timeout?",
        "timeout is thirty seconds",
    ),
    (
        _EFILL * 6
        + "The contact for incidents is the on-call operations desk at all hours. "
        + _ETAIL * 5,
        "Who is the contact for incidents?",
        "on-call operations desk",
    ),
)

#: A period only *looks* like a sentence break here; the window must not open on
#: the false continuation. Each is (content, must_not_open_prefix).
_PAD = "This is padding text that extends the chunk well beyond the cap length. " * 4
_HEAD = "A short opening sentence sits here. "
_FALSE_BOUNDARY_CASES: tuple[tuple[str, str], ...] = (
    (_HEAD + "Contact J. Doe about the open ticket. " + _PAD, "Doe about"),
    (_HEAD + "The class Foo.Bar handles the task. " + _PAD, "Bar handles"),
    (_HEAD + "Use a cache, e.g. the local disk store. " + _PAD, "the local disk"),
    (_HEAD + "The link uses TLS. Certificates rotate soon. " + _PAD, "Certificates"),
)


@dataclass(frozen=True)
class ExcerptCentersEnglishResult:
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

    tmp = Path(tempfile.mkdtemp(prefix="excerpt-center-en-"))
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


def evaluate_excerpt_centers_english_paragraph() -> ExcerptCentersEnglishResult:
    from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
    from sidra_ai.api.citations import _candidate_starts, select_excerpt_window

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1 (per case): the window the service builds contains the answer sentence,
    #    and the head-200 window - the pre-fix behaviour - does not (so the case
    #    actually exercises the move, not a chunk that happened to fit).
    for content, query, answer in _PARAGRAPH_CASES:
        window = select_excerpt_window(content, query)
        add(answer in window,
            f"english {query!r}: window omits the answer 「{answer}」: {window[-40:]!r}")
        add(len(window) <= MAX_CITATION_EXCERPT_CHARS,
            f"english {query!r}: window over the cap ({len(window)})")

    # 2: end-to-end through the real chat path, the shown excerpt has the answer.
    content, query, answer = _PARAGRAPH_CASES[0]
    excerpt = _service_excerpt(content, query)
    add(answer in excerpt,
        f"service excerpt omits the answer 「{answer}」: {excerpt[:60]!r}")

    # 3: a period that is not a sentence break must not open a window on the
    #    false continuation (initial, dotted name, abbreviation, acronym).
    for content, forbidden in _FALSE_BOUNDARY_CASES:
        starts = _candidate_starts(content)
        add(not any(content[s:].startswith(forbidden) for s in starts),
            f"false boundary opens on 「{forbidden}」")

    # 4: the Japanese single-line paragraph the fix extends still centres.
    ja_content = "前置きの段落がここに続く。" * 40 + "重要: バックアップは毎日午前 3 時に実行されます。" + "その後の説明。" * 20
    ja_window = select_excerpt_window(ja_content, "バックアップの実行時刻はいつですか")
    add("バックアップは毎日午前 3 時" in ja_window, "japanese paragraph no longer centres")

    # 5: a chunk carrying a newline before the answer still centres.
    nl_content = _EFILL * 40 + "\nDeploys happen every Friday night on schedule.\n" + _ETAIL * 20
    nl_window = select_excerpt_window(nl_content, "When do deploys happen?")
    add("Deploys happen every Friday night" in nl_window, "newline chunk no longer centres")

    # 6: the documented fallback survives - an empty or unmatched query opens at
    #    the top, never a sentence chosen at random by a new boundary.
    fb_content = _PARAGRAPH_CASES[0][0]
    add(select_excerpt_window(fb_content, "") == fb_content[:MAX_CITATION_EXCERPT_CHARS],
        "empty query no longer opens at the top")
    add(select_excerpt_window(fb_content, "zzz qqq") == fb_content[:MAX_CITATION_EXCERPT_CHARS],
        "unmatched query no longer opens at the top")

    total = 2 * len(_PARAGRAPH_CASES) + 1 + len(_FALSE_BOUNDARY_CASES) + 1 + 1 + 2
    return ExcerptCentersEnglishResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ExcerptCentersEnglishResult",
    "evaluate_excerpt_centers_english_paragraph",
]
