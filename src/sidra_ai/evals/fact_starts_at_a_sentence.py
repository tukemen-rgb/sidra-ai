"""Do the facts in a generated report start where a sentence starts?

C-1534: of the bullets under 「わかっていること」 in four generated reports,
measured over the five indexed repositories on 2026-09-14, **3 of 11 started at
the head of a sentence** - the other eight opened with 「…」 and read, to the
president pasting them into a deck, as text broken off mid-thought:

    - …| 本稼働 | 加えて NEXT_PUBLIC_ADSENSE_ACTIVE=1 | …
    - …3. /out/<id> 経由の広告主様リンク 1 本 …

The filing put the cause at the window's start position and proposed advancing
it to a sentence boundary. Measured, that was not the cause: of the 20 excerpt
windows those reports were built from, **19 already opened at a sentence end, a
heading, a list item, a table row or a paragraph break**. The two bullets above
begin at a table row and at an ordered-list item - clean places both. What was
broken was the *mark*: 「…」 was written whenever the window was not the head of
the chunk, which is true about the chunk and false about the sentence, and on a
report bullet the reader only ever sees the sentence.

So the fix is at the seam that already cuts the tail back to a whole sentence
(``whole_sentences``, C-1213): ``clean_head`` reserves 「…」 for a head that is
genuinely mid-sentence. The /v1/chat citation excerpt is deliberately left
alone - there 「…」 tells an operator they are looking at a slice (C-1264).

Both directions, because a metric that only counted missing 「…」 marks would
score full on a change that deleted the mark outright:

* a report built from hard-wrapped prose has its facts start at a sentence;
* a window that really does open mid-sentence still says so with 「…」;
* and the evidence survives - the retrieved term is still in the fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_ELLIPSIS = "…"

#: A subject the corpus below genuinely carries, so the report has facts.
_REQUEST = "広告の方針のレポートを作って"

#: The opening of the one fact below that really is cut mid-sentence, used to
#: tell the marks that must be there from the marks that must not.
_WRAPPED_HEAD = "あって、"

#: The corpus has to be able to *fail*. ``qa_honesty``'s chunks are 53-126
#: characters, all inside ``MAX_CITATION_EXCERPT_CHARS``, so no window is ever
#: clipped and no head can be ragged - a report built from it passed this eval
#: with the fix reverted. These documents carry the three shapes the five real
#: repositories actually carry past the cap: a Markdown table, an ordered list,
#: a sentence opening mid-line right after a 「。」 (the commonest shape of all -
#: 6 of those 20 - and the one that makes the terminator rule testable),
#: Japanese prose hard-wrapped mid-sentence, and a plain paragraph opening after
#: a blank line (the line before it ends in 「:」, so only the paragraph break
#: makes it a clean start - without that shape, deleting the paragraph-break
#: rule changed no number here, which is a blind check, not a safe rule).
#: Each is long enough that the window opens well inside the chunk.
_FILLER = "この節では運営の一般的な background を説明しています。"
_DOCUMENTS: tuple[tuple[str, str], ...] = (
    (
        "docs/ads-table.md",
        "## 運用の記録\n\n"
        + _FILLER * 8
        + "\n\n| 区分 | 設定 | 効果 |\n| --- | --- | --- |\n"
        "| 本稼働 | ADSENSE を有効にする | 広告と方針の新文面が有効になる |\n"
        "| 審査中 | 広告の方針は掲載のみ | 表示はまだ始まらない |\n\n"
        + _FILLER * 8,
    ),
    (
        "docs/ads-list.md",
        "## 掲載の内訳\n\n"
        + _FILLER * 8
        + "\n\n1. トップページの広告枠 1 本\n"
        "2. 記事下の広告枠 1 本\n"
        "3. 広告の方針ページへの導線 1 本\n\n"
        + _FILLER * 8,
    ),
    (
        "docs/ads-sentences.md",
        "## 記録\n\n"
        + "運営の一般的な経緯をここに記録しています。" * 10
        + "広告の方針はこの文で初めて述べられます。続く一文がここに入ります。"
        + "さらに記録が続きます。" * 10,
    ),
    (
        "docs/ads-paragraph.md",
        "## 掲載の狙い\n\n"
        + _FILLER * 8
        + "\n\n報道されている狙い:\n\n"
        "広告の方針はここで示されている。続く説明がここに入ります。\n\n"
        + _FILLER * 8,
    ),
    (
        "docs/ads-prose.md",
        "## 方針の背景\n\n"
        + _FILLER * 8
        + "\n\nこの段落は一行に収まらないので途中で折り返されていて\n"
        "あって、広告の方針そのものはここで述べられている。次の文はここから始まる。\n\n"
        + _FILLER * 8,
    ),
)


def _build_service():
    """A real ``SidraService`` over the corpus above, through the real gate."""

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.evals.scratch import scratch_dir
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(scratch_dir(prefix="fact-starts-"))
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
    for path, content in _DOCUMENTS:
        store.add(
            Document(
                content=content,
                provenance=Provenance(
                    source="github",
                    repository=repository,
                    path=path,
                    commit_sha="e" * 40,
                    timestamp=datetime(2026, 9, 14, tzinfo=timezone.utc),
                    source_type=SourceType.DOCS,
                    trust_level=TrustLevel.INTERNAL_REPO,
                    license="proprietary",
                ),
            )
        )
    return SidraService(settings, store=store, gate=gate)


@dataclass(frozen=True)
class FactStartsAtASentenceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    #: The rate the board asked for: facts whose text begins where a sentence
    #: begins, over facts in the report. Reported rather than scored, because a
    #: fact that really is cut mid-sentence *should* count against it and still
    #: be shown - the checks are what say which is which.
    facts_total: int = 0
    facts_clean: int = 0


def _report_bullets() -> tuple[list[str], str]:
    """The 「わかっていること」 bullets of a real generated report."""

    service = _build_service()
    result = service.chat(_REQUEST)
    outcome = (result.get("creation") or {}).get("outcome") or {}
    artifact = Path(outcome.get("artifact_path", ""))
    if not artifact.is_file():
        return [], "document request produced no artifact"
    markdown = artifact.read_text(encoding="utf-8")
    body = markdown.split("## わかっていること", 1)[-1].split("## まだ", 1)[0]
    bullets = [
        line.strip()[2:]
        for line in body.splitlines()
        if line.strip().startswith("- ")
    ]
    return bullets, ""


def evaluate_fact_starts_at_a_sentence() -> FactStartsAtASentenceResult:
    from sidra_ai.api.citations import citation_excerpt
    from sidra_ai.security.output_guard import OutputGuard

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    bullets, problem = _report_bullets()
    if problem:
        return FactStartsAtASentenceResult(False, 0, 5, (problem,))
    add(bool(bullets), "the report carried no facts to judge")

    # The number the item is about. The table and list documents are clipped
    # exactly as the prose one is - the window opens well inside the chunk -
    # but they open on a row and on an ordered item, which is where a reader
    # would open too, so nothing about them is broken and nothing should say
    # it is.
    ragged = [b for b in bullets if b.startswith(_ELLIPSIS)]
    mismarked = [b for b in ragged if _WRAPPED_HEAD not in b[: len(_WRAPPED_HEAD) + 2]]
    add(
        not mismarked,
        f"{len(mismarked)}/{len(bullets)} report facts start mid-sentence: "
        + "; ".join(b[:40] for b in mismarked[:3]),
    )

    # And the other direction, through the same report rather than a unit call:
    # the one fact that really does open in the middle of a sentence has to keep
    # saying so. Without this, deleting the mark scores full marks.
    wrapped = [b for b in bullets if _WRAPPED_HEAD in b[: len(_WRAPPED_HEAD) + 2]]
    add(
        bool(wrapped) and all(b.startswith(_ELLIPSIS) for b in wrapped),
        "the hard-wrapped fact lost its 「…」 (or was not retrieved): "
        + "; ".join(b[:40] for b in wrapped[:2]),
    )

    guard = OutputGuard()

    # The evidence must survive the rule. This paragraph is hard-wrapped, so the
    # line the window opens on is the back half of a sentence - and the query
    # term sits in that half, so advancing past it would buy a tidy head by
    # throwing the reason the chunk was retrieved away.
    wrapped_chunk = (
        "前置きの段落です。" * 8
        + "\nこの行は前の行の続きで\n"
        + "あって、ペンギンの飼育について述べている。次の文はここから始まる。\n"
        + "後続の段落が続きます。" * 12
    )
    ex_wrapped, _ = citation_excerpt(wrapped_chunk, guard, "ペンギン", clean_head=True)
    add(
        "ペンギン" in ex_wrapped,
        f"the retrieved term was polished out of the excerpt: 「{ex_wrapped[:40]}」",
    )

    # And a clipped head that opens on a table row keeps no mark, while the
    # clipped tail keeps its own: the head rule must not eat the tail rule.
    table = (
        "冒頭の無関係な文がここに置かれています。" * 4
        + "\n| 区分 | 内容 |\n| --- | --- |\n| セキュリティ規約 | ペンギンの飼育は許可制 |\n"
        + "後続の説明がここから続きます。" * 12
    )
    ex_table, _ = citation_excerpt(table, guard, "セキュリティ規約", clean_head=True)
    add(
        not ex_table.startswith(_ELLIPSIS) and ex_table.endswith(_ELLIPSIS),
        "a table-row head was marked, or the tail mark was lost: "
        f"「{ex_table[:20]} … {ex_table[-12:]}」",
    )

    return FactStartsAtASentenceResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=5,
        failures=tuple(failures),
        facts_total=len(bullets),
        facts_clean=len(bullets) - len(ragged),
    )


__all__ = ["FactStartsAtASentenceResult", "evaluate_fact_starts_at_a_sentence"]
