"""Do generated decks and documents quote evidence as prose, not Markdown?

C-1212: the corpus is Markdown, and the 200-character excerpt window lands
mid-document - so slide bullets read 「## 運用メモ」「**事前に本人へ一言**」
「> インディーゲーム…」 with the decoration as literal characters. Facts are
flattened once, where they are made (``_facts_for``); the /v1/chat citation
excerpts stay raw on purpose so a reviewer can match them to the source.

Measured through the real chat path over a Markdown-heavy corpus, both
directions: the decoration is gone from the artifacts AND the quoted words
survive - an over-eager stripper that eats evidence would be a worse bug
than the one it fixes.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class FactTextPlainResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


_MARKDOWN_DOC = (
    "## 運用メモ\n\n"
    "> 掲載実績は 21,907 件。**事前に本人へ一言** を徹底する。\n"
    "運用の合言葉は `normalize` を通すこと。**毎日 1 本** 出す。\n"
)


def _build_service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(tempfile.mkdtemp(prefix="fact-plain-"))
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
            content=_MARKDOWN_DOC,
            provenance=Provenance(
                source="github",
                repository=repository,
                path="docs/ops.md",
                commit_sha="f" * 40,
                timestamp=datetime(2026, 9, 3, tzinfo=timezone.utc),
                source_type=SourceType.DOCS,
                trust_level=TrustLevel.INTERNAL_REPO,
                license="proprietary",
            ),
        )
    )
    return SidraService(settings, store=store, gate=gate)


def evaluate_fact_text_plain() -> FactTextPlainResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    artifacts: dict[str, str] = {}
    for label, request in (
        ("deck", "運用メモの実績を紹介するデッキを作って"),
        ("document", "運用メモのレポートを作って"),
    ):
        outcome = (service.chat(request).get("creation") or {}).get("outcome") or {}
        path = Path(outcome.get("artifact_path", ""))
        if outcome.get("handled") and path.is_file():
            checks += 1
            artifacts[label] = path.read_text(encoding="utf-8")
        else:
            failures.append(f"{label}: not generated")

    for label, body in artifacts.items():
        # Decoration must not appear inside quoted evidence. The document
        # artifact is itself Markdown, so its own structure (# title,
        # ## sections, the generator's one "> SIDRA AI…" byline) is fine -
        # what may not appear is decoration *inside* an evidence line: bold
        # stars anywhere (no generator emits them), heading hashes or quote
        # markers mid-line (an excerpt dragging its source's markup along).
        if label == "deck":
            offending = [
                line for line in body.splitlines()
                if "**" in line or " ## " in line or "&gt; " in line
            ]
        else:
            offending = [
                line for line in body.splitlines()
                if "**" in line
                or (line.startswith("- ") and ("## " in line or "> " in line))
            ]
        if not offending:
            checks += 1
        else:
            failures.append(f"{label}: markdown leaked: {offending[0][:60]!r}")
        if "事前に本人へ一言" in body and "21,907" in body and "normalize" in body:
            checks += 1
        else:
            failures.append(f"{label}: quoted words were eaten by the stripper")

    return FactTextPlainResult(
        passed=not failures, checks_passed=checks, checks_total=6,
        failures=tuple(failures),
    )
