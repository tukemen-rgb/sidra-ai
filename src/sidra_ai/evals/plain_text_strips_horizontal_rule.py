"""Does answer/evidence flattening strip a `***` / `___` horizontal rule?

C-1886, the next case in the C-1695 (fenced code) / C-1709 (setext underline)
family: a line-level Markdown decoration leaking into flattened evidence. A
thematic break (horizontal rule) has three spellings - `---`, `***`, `___` - and
only the dash form was removed (by ``_MD_TABLE_SEP``, which drops a ``-{2,}``
line). ``***`` fell to the dangling-bold cleanup and left a lone ``*``; ``___``
was untouched and survived as a raw ``___``. Both are pure syntax with no content,
so ``プロローグ\n***\n本編`` flattened to 「プロローグ * 本編」 and the ``___`` form
to 「… ___ …」 - the same artifact class as the fence and setext bugs. ``plain_text``
now removes an all-``*`` or all-``_`` rule line (spaced variants too) while keeping
the surrounding text.

The checks drive ``plain_text`` directly and the real ``/v1/chat``: the rule
leaves no artifact, the text around it survives, spaced variants go too, inline
emphasis and a two-star ``**`` are not over-stripped, and a real answer over such
a document carries no artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sidra_ai.evals.scratch import scratch_dir


def _chat_answer(message: str, doc_content: str) -> str:
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    gate = SecurityGate(GatePolicy(), allowed_repositories=("acme/h",))
    store = DocumentStore(gate)
    prov = Provenance(
        source="github", repository="acme/h", path="a.md", commit_sha="abc1234",
        timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
    )
    store.add(Document(content=doc_content, provenance=prov))
    settings = Settings(data_dir=scratch_dir())
    service = SidraService(settings, model=EchoModelAdapter(), store=store, gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    return client.post("/v1/chat", json={"message": message}).json().get("answer", "")


@dataclass(frozen=True)
class HorizontalRuleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_plain_text_strips_horizontal_rule() -> HorizontalRuleResult:
    from sidra_ai.creation.evidence import plain_text

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) a `***` rule leaves no * artifact; the text around it survives ---
    star = plain_text("プロローグ\n\n***\n\n本編が始まる。")
    add("*" not in star and "プロローグ" in star and "本編が始まる" in star,
        f"A: a *** rule left an artifact or dropped text: {star!r}")

    # --- (B) a `___` rule leaves no _ artifact; the text survives ---
    under = plain_text("序文の段落。\n\n___\n\n次の段落。")
    add("___" not in under and "序文の段落" in under and "次の段落" in under,
        f"B: a ___ rule left an artifact or dropped text: {under!r}")

    # --- (C) spaced variants (`* * *`, `_ _ _`) are removed too ---
    spaced = plain_text("上。\n\n* * *\n\n中。\n\n_ _ _\n\n下。")
    add("*" not in spaced and "_" not in spaced
        and "上" in spaced and "中" in spaced and "下" in spaced,
        f"C: a spaced rule survived: {spaced!r}")

    # --- (D) inline emphasis and a two-star ** are not over-stripped ---
    emph = plain_text("これは *重要* な __設定__ です。")
    add("重要" in emph and "設定" in emph,
        f"D: inline emphasis text was dropped: {emph!r}")
    math = plain_text("面積は 3 * 4 = 12 です。")
    add("3 * 4 = 12" in math, f"D: a mid-line * was over-stripped: {math!r}")

    # --- (E) a real /v1/chat answer over a rule doc carries no artifact ---
    doc = "設定の概要。\n\n***\n\nデフォルトのポートは 8080 です。\n"
    answer = _chat_answer("デフォルトのポートは？", doc)
    add("8080" in answer and " * " not in answer,
        f"E: the chat answer carried a rule artifact: {answer[:160]!r}")

    # --- (F) plain prose is unchanged (no over-stripping) ---
    prose = "ただの文章です。句点で終わる。"
    add(plain_text(prose) == prose, "F: plain prose was altered")

    total = 7
    return HorizontalRuleResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["HorizontalRuleResult", "evaluate_plain_text_strips_horizontal_rule"]
