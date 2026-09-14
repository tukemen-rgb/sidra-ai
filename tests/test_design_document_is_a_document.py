"""A design document is a document.

C-1809. 仕様書, 要件定義書, 提案書, 報告書, 議事録 and マニュアル all reach the
document generator; 設計書 did not, so 「設計書を作って」 was met with 「この形式は
作れません。いま作れるのは … レポート …」 - declined by a sentence naming the
generator that would have written it, which is C-1804's self-contradiction one
kind along. A design document about indexed code is what this generator makes.

企画書 and 計画書 were measured in the same cycle and left alone on purpose.
They fall under an exclusion note whose pinned case is 「事業計画書」, and a
business plan written from nothing is not what an evidence-grounded generator
produces - the prior loops' decline is the honest answer there. Those cases are
asserted below so this change is measured as not having reached them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.intent import CreationKind, detect_creation_intent  # noqa: E402


def kind_of(message: str):
    found = detect_creation_intent(message)
    return found.kind if found else None


@pytest.mark.parametrize(
    "message", ["設計書を作って", "ゲームの設計書を作って", "基本設計書を作って"]
)
def test_a_design_document_reaches_the_document_generator(message: str) -> None:
    assert kind_of(message) is CreationKind.DOCUMENT


@pytest.mark.parametrize(
    "message", ["仕様書を作って", "要件定義書を作って", "提案書を作って", "議事録を作って"]
)
def test_the_siblings_that_already_worked_still_do(message: str) -> None:
    """Without this, deleting every cue would satisfy the test above vacuously."""

    assert kind_of(message) is CreationKind.DOCUMENT


@pytest.mark.parametrize("message", ["事業計画書を作って", "企画書を作って", "計画書を作って"])
def test_the_business_plan_exclusion_is_not_reached(message: str) -> None:
    """C-1263's line, kept deliberately.

    A plan written from nothing is not what an evidence-grounded generator
    makes, so declining is the honest answer and this change must not touch
    it. Asserted rather than merely avoided.
    """

    assert kind_of(message) is not CreationKind.DOCUMENT


@pytest.mark.parametrize("message", ["企画書一式を作って", "ゲームを企画から作って"])
def test_the_production_bundle_is_untouched(message: str) -> None:
    assert kind_of(message) is CreationKind.PROJECT


def test_the_eval_counts_a_failure_into_its_denominator() -> None:
    """Driven against a broken cue list: the equality is vacuous while all pass."""

    import sidra_ai.creation.intent as intent_mod
    from sidra_ai.evals import design_document_is_a_document as mod

    healthy = mod.evaluate_design_document_is_a_document()
    assert healthy.passed and healthy.checks_total == healthy.checks_passed

    original = intent_mod._ARTIFACTS[CreationKind.DOCUMENT]
    intent_mod._ARTIFACTS[CreationKind.DOCUMENT] = tuple(
        w for w in original if w != "設計書"
    )
    try:
        broken = mod.evaluate_design_document_is_a_document()
    finally:
        intent_mod._ARTIFACTS[CreationKind.DOCUMENT] = original

    assert not broken.passed
    assert broken.checks_passed < healthy.checks_passed
    assert broken.checks_total == healthy.checks_total
