"""Does a generated document print only facts about what was asked for?

C-1201 put a floor under the *answer* path: BM25's CJK bigrams fill
``top_k`` on cross-word glue, so a question about the weather came back as
cited marketing copy. The generators never got the same floor, and a
document is where its absence shows worst - a weekly-report request would
print jam-making steps under 「わかっていること」, each with a source label
beside it, which is the shape a reader trusts most.

Measured through the real ``chat`` path, for the same reason C-1201's eval
does: removing the filter from the job is the most likely way this
regresses, and a probe that re-implemented the routing would stay green
while the product broke.

Three things are checked per request, because two of them can be right
while the product is broken:

* The document contains **none** of the unrelated subject's own words.
* It still contains the **related** ones. A filter that dropped everything
  would pass the first check and hand back an empty skeleton, which is the
  failure C-1202's honest abstention exists for rather than a success.
* Retrieval **did** hand over a mixture this run. Without this the eval
  scores its own corpus rather than the filter: four earlier corpora here
  reported nothing set aside, so both checks above passed with the filter
  removed. A run where nothing was mixed is reported as a failure, not a
  clean sheet.

Both subjects are asked for, so neither one gets to be the permanent
intruder - the filter has to be right about whichever was requested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sidra_ai.documents import Provenance, SourceType, TrustLevel

#: The glue that makes the failure reachable. 「〜についてのレポートを
#: まとめて作って」 is a request, not a subject, and BM25's CJK bigrams score
#: it: a passage that repeats it outranks one that only knows the subject.
#: Real docs pages carry this phrasing, and a corpus without it never hands
#: the generator a mixture at all - four earlier corpora here reported
#: ``off_topic=0`` for exactly that reason, i.e. they measured nothing.
_GLUE = "についてのレポートをまとめて作っての手順です。"

#: Two subjects that share no content word, each glue-saturated so either
#: one can be the intruder. Asked about weekly reports, retrieval hands over
#: jam passages; asked about jam, it hands over weekly ones.
_MIXED: tuple[tuple[str, str], ...] = tuple(
    [
        (
            f"週報{_GLUE * 4}今週の売上が 120 万円だったことを並べます。",
            f"docs/weekly-{index}.md",
        )
        for index in range(4)
    ]
    + [
        (
            f"ジャム{_GLUE * 4}砂糖を加えて煮詰め、瓶を煮沸します。",
            f"recipes/jam-{index}.md",
        )
        for index in range(4)
    ]
)

#: Words that belong to each subject and to no other. Checked in the
#: document body: a fact is present when its own vocabulary is.
_JAM_WORDS = ("ジャム", "砂糖", "煮沸")
_WEEKLY_WORDS = ("週報", "売上")

#: The path prefix each subject's passages live under. Checked in the
#: 出典 list, which is the claim a reader actually acts on: a repository
#: path printed beside a report is a promise that the report came from it.
_JAM_PATH = "recipes/jam"
_WEEKLY_PATH = "docs/weekly"

#: The two requests, each paired with what it must print and what it must
#: not. Both use the glue phrasing on purpose - it is what a person
#: actually types, and it is what makes the corpus mix.
_REQUESTS: tuple[tuple[str, tuple[str, ...], str, tuple[str, ...], str], ...] = (
    (
        "週報についてのレポートをまとめて作って",
        _WEEKLY_WORDS,
        _WEEKLY_PATH,
        _JAM_WORDS,
        _JAM_PATH,
    ),
    (
        "ジャムについてのレポートをまとめて作って",
        _JAM_WORDS,
        _JAM_PATH,
        _WEEKLY_WORDS,
        _WEEKLY_PATH,
    ),
)

#: The two sections a reader treats as claims. The title and 概要 quote the
#: request back verbatim, so a whole-body word search finds the subject
#: whether or not a single fact survived - a filter that dropped everything
#: read as "kept its own evidence" until these sections were split out.
_EVIDENCE_HEADING = "わかっていること"
_SOURCES_HEADING = "出典"


@dataclass(frozen=True)
class TopicalityResult:
    passed: bool
    #: Documents that printed no word belonging to the other subject.
    clean: int
    #: Requests asked, i.e. the denominator for all three counts.
    mixed_total: int
    #: ...and still printed their own subject's words.
    kept: int
    #: ...and were built from a run where retrieval really did hand over
    #: unrelated evidence. Below ``mixed_total`` the corpus stopped
    #: reproducing the failure and the other two counts prove nothing.
    mixed: int = 0
    failures: tuple[str, ...] = ()

    @property
    def checks_total(self) -> int:
        return 3 * self.mixed_total

    @property
    def checks_passed(self) -> int:
        return self.clean + self.kept + self.mixed


def _provenance(path: str) -> Provenance:
    return Provenance(
        source="github",
        repository="tukemen-rgb/sidra-ai",
        path=path,
        commit_sha="d" * 40,
        timestamp=datetime(2026, 9, 3, tzinfo=timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )


def _build_service():
    """A real service over the mixed corpus, echo backend."""

    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(tempfile.mkdtemp(prefix="doc-topicality-"))
    repository = "tukemen-rgb/sidra-ai"
    settings = Settings(allowed_repositories=(repository,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repository,),
        quarantine_store=QuarantineStore(tmp / "quarantine.jsonl"),
    )
    store = DocumentStore(gate)
    for content, path in _MIXED:
        store.add(Document(content=content, provenance=_provenance(path)))
    return SidraService(settings, store=store, gate=gate)


def _section(body: str, heading: str) -> str:
    """The lines under ``## <heading>``, up to the next heading."""

    marker = f"## {heading}"
    start = body.find(marker)
    if start < 0:
        return ""
    rest = body[start + len(marker) :]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def _document_of(result: dict) -> str:
    path = ((result.get("creation") or {}).get("outcome") or {}).get("artifact_path") or ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def evaluate_document_topicality() -> TopicalityResult:
    """Ask for each subject over a corpus that also knows the other one."""

    service = _build_service()
    failures: list[str] = []
    clean = kept = mixed = 0

    for request, own_words, own_path, other_words, other_path in _REQUESTS:
        creation = (service.chat(request) or {}).get("creation") or {}
        details = (creation.get("outcome") or {}).get("details") or {}
        body = _document_of({"creation": creation})
        label = request[:6]

        if not body:
            failures.append(f"{label}: no document was produced at all")
            continue

        evidence = _section(body, _EVIDENCE_HEADING)
        sources = _section(body, _SOURCES_HEADING)
        if not evidence and not sources:
            failures.append(
                f"{label}: the document has neither a 「{_EVIDENCE_HEADING}」 nor a "
                f"「{_SOURCES_HEADING}」 section, so there is nothing to judge"
            )
            continue

        strays = [word for word in other_words if word in evidence]
        if other_path in sources:
            strays.append(other_path)
        if strays:
            failures.append(f"{label}: the document claimed {strays}")
        else:
            clean += 1

        # The other direction: a filter that dropped everything leaves the
        # request echoed in the title and 概要 and nothing under either
        # heading, which is C-1202's abstention, not a clean report.
        if any(word in evidence for word in own_words) and own_path in sources:
            kept += 1
        else:
            failures.append(f"{label}: the document kept none of its own evidence")

        # Did the filter have anything to do? If retrieval stopped mixing,
        # the two checks above are measuring the corpus, not the product.
        if details.get("off_topic_facts"):
            mixed += 1
        else:
            failures.append(
                f"{label}: nothing was set aside, so the corpus no longer mixes "
                "and this run proves nothing"
            )

    return TopicalityResult(
        passed=not failures,
        clean=clean,
        mixed_total=len(_REQUESTS),
        kept=kept,
        mixed=mixed,
        failures=tuple(failures),
    )


__all__ = ["TopicalityResult", "evaluate_document_topicality"]
