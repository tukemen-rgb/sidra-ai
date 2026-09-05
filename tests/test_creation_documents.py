"""A generated report is grounded or blank - never plausible.

Same rule as the deck, tested the same way: numbers on the page must have
arrived in a retrieved fact, an empty retrieval produces an honest skeleton
rather than filler, and the validator's fabrication check is itself tested
against a document that cheats.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.creation.documents import (
    BLANK,
    GeneratedDocument,
    generate_document,
    save_document,
    validate_document,
)
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.creation.router import build_default_router

FACTS = [
    Fact("索引した文書が 482 件ある", "tukemen-rgb/sidra-ai docs/OUTCOMES.md"),
    Fact("回答には引用が付く", "tukemen-rgb/sidra-ai docs/ARCHITECTURE.md"),
]


def test_a_grounded_report_carries_facts_with_their_sources() -> None:
    document = generate_document("進捗レポートを作って", facts=FACTS)
    verdict = validate_document(document, FACTS)

    assert verdict["usable"], verdict["failures"]
    assert "482" in document.markdown
    assert "docs/OUTCOMES.md" in document.markdown
    # The trailing document-kind word is dropped from the title (C-1246): the
    # file is a report, so 「進捗レポート」 would say 「レポート」 twice (heading,
    # 概要 and confirmation). The subject alone titles it.
    assert document.markdown.startswith("# 進捗\n")


def test_an_empty_retrieval_produces_blanks_not_filler() -> None:
    document = generate_document("レポートを作って")
    verdict = validate_document(document, [])

    assert verdict["usable"], verdict["failures"]
    assert BLANK in document.markdown
    assert "概要" in document.unfilled
    # No number reached the page from nowhere.
    assert not re.search(r"\d", document.markdown.split("## ", 1)[-1])


def test_an_invented_number_fails_validation() -> None:
    """The fabrication check has to actually fire, or it is decoration."""

    honest = generate_document("レポートを作って", facts=FACTS)
    cheat = GeneratedDocument(
        title=honest.title,
        markdown=honest.markdown.replace("482 件", "9999 件"),
        unfilled=honest.unfilled,
        evidence=honest.evidence,
    )

    verdict = validate_document(cheat, FACTS)

    assert not verdict["usable"]
    assert any("9999" in failure for failure in verdict["failures"])


def test_the_unknowns_section_is_always_present() -> None:
    """A report that cannot say what it does not know claims to know everything."""

    document = generate_document("レポートを作って", facts=FACTS)
    assert "## まだ埋まっていないこと" in document.markdown
    assert "まだ埋まっていないこと" in document.unfilled


def test_save_writes_markdown_the_listing_will_carry(tmp_path) -> None:
    from sidra_ai.api.artifacts import SAFE_NAME

    document = generate_document("レポートを作って", facts=FACTS)
    path = save_document(document, tmp_path)

    assert path.exists()
    assert SAFE_NAME.match(path.name)
    assert path.suffix == ".md"


def test_intent_routes_document_requests_but_not_questions() -> None:
    assert detect_creation_intent("進捗レポートを作って").kind is CreationKind.DOCUMENT
    assert detect_creation_intent("報告書を書いて").kind is CreationKind.DOCUMENT
    assert not detect_creation_intent("レポートの書き方を教えて").is_creation


def test_router_builds_a_document_end_to_end(tmp_path) -> None:
    router = build_default_router(data_dir=str(tmp_path))
    request = "進捗レポートを作って"
    outcome = router.route(request, detect_creation_intent(request), FACTS)

    assert outcome.handled
    assert outcome.details["usable"] is True
    assert outcome.details["sources"] == 2
    assert outcome.artifact_path.endswith(".md")


def test_every_detected_kind_now_has_a_generator(tmp_path) -> None:
    """The C-1005 claim itself: nothing the detector recognises is unroutable.

    Enumerated from the enum, so adding a kind to the detector without a
    generator breaks this test rather than shipping a dead end.
    """

    router = build_default_router(data_dir=str(tmp_path))
    registered = set(router.registered_kinds())
    detectable = {kind.value for kind in CreationKind if kind is not CreationKind.UNKNOWN}

    assert registered == detectable
