"""Do deck and document bullets end at a sentence, not mid-word?

C-1213: the excerpt window starts at a line boundary by design but ends at
a hard 200-character cap, so slide bullets ended 「…予約投」「…投稿し」.
Generator-bound facts are now trimmed back to their last complete sentence
- and only trimmed: text with no terminator, or whose only terminator sits
too close to the head, passes through whole, because a fragment with
content beats an empty polish.

Measured through the real chat path over a corpus built to produce both
shapes: a long Markdown document whose 200-character window must land
mid-sentence, and a short terminator-free note that must survive intact.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SENTENCE_ENDS = "。．.!?！？"

#: One long paragraph: sentences of ~60 chars each, so any 200-char window
#: ends inside a sentence unless someone trims it.
_LONG_DOC = "運用メモの基本方針。" + "".join(
    f"運用メモの第{i}条は掲載実績の数字を毎週確かめてから資料に載せることを求めている。"
    for i in range(1, 9)
)

#: No terminator at all: the trim must leave this fact alone.
_FRAGMENT_DOC = "運用メモの合言葉一覧: 正直第一 数字は実測 出典を添える 推測で埋めない 断片も残す"


@dataclass(frozen=True)
class FactWholeSentencesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service_over(content: str, path: str):
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(tempfile.mkdtemp(prefix="whole-sentences-"))
    repository = "tukemen-rgb/sidra-ai"
    settings = Settings(allowed_repositories=(repository,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=(repository,),
        quarantine_store=QuarantineStore(tmp / "quarantine.jsonl"),
    )
    store = DocumentStore(gate)
    store.add(
        Document(
            content=content,
            provenance=Provenance(
                source="github",
                repository=repository,
                path=path,
                commit_sha="a" * 40,
                timestamp=datetime(2026, 9, 3, tzinfo=timezone.utc),
                source_type=SourceType.DOCS,
                trust_level=TrustLevel.INTERNAL_REPO,
                license="proprietary",
            ),
        )
    )
    return SidraService(settings, store=store, gate=gate)


def evaluate_fact_whole_sentences() -> FactWholeSentencesResult:
    checks = 0
    failures: list[str] = []

    # Shape 1: the long document. Every quoted bullet in the generated
    # document must end at a sentence terminator.
    service = _service_over(_LONG_DOC, "docs/long.md")
    outcome = (service.chat("運用メモのレポートを作って").get("creation") or {}).get("outcome") or {}
    path = Path(outcome.get("artifact_path", ""))
    if outcome.get("handled") and path.is_file():
        checks += 1
        body = path.read_text(encoding="utf-8")
        quoted = [
            line for line in body.splitlines()
            if line.startswith("- ") and "（出典: " in line
        ]
        if quoted and all(
            line[: line.rindex("（出典: ")].rstrip()[-1:] in _SENTENCE_ENDS
            for line in quoted
        ):
            checks += 1
        else:
            bad = [l for l in quoted if l[: l.rindex("（出典: ")].rstrip()[-1:] not in _SENTENCE_ENDS]
            failures.append(f"a bullet still ends mid-sentence: {bad[0][-40:]!r}" if bad
                            else "no quoted bullets were produced")
        if "運用メモの第" in body:
            checks += 1
        else:
            failures.append("the trim removed the quoted content itself")
    else:
        failures.append("long-doc report not generated")

    # Shape 2: the terminator-free note must come through untrimmed.
    service = _service_over(_FRAGMENT_DOC, "docs/fragment.md")
    outcome = (service.chat("運用メモのレポートを作って").get("creation") or {}).get("outcome") or {}
    path = Path(outcome.get("artifact_path", ""))
    if outcome.get("handled") and path.is_file():
        body = path.read_text(encoding="utf-8")
        if "断片も残す" in body:
            checks += 1
        else:
            failures.append("a terminator-free excerpt was trimmed away")
    else:
        failures.append("fragment report not generated")

    return FactWholeSentencesResult(
        passed=not failures, checks_passed=checks, checks_total=4,
        failures=tuple(failures),
    )
