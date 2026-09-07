"""C-1458: common Japanese document requests build a document, not a Q&A miss.

議事録/マニュアル/提案書/仕様書/要件定義書/手順書/説明書 now route to the DOCUMENT
generator; business-plan wording (企画/計画) is left out so the C-1263 boundary
with the game-production bundle is unmoved.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.evals.document_deliverables_route import (
    evaluate_document_deliverables_route,
)


def test_document_deliverables_eval_passes():
    result = evaluate_document_deliverables_route()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize(
    "message",
    ["会議の議事録を作って", "操作マニュアルを作って", "新機能の提案書を作って", "APIの仕様書を作って"],
)
def test_document_requests_route_to_document(message: str):
    intent = detect_creation_intent(message)
    assert intent.routes
    assert intent.kind is CreationKind.DOCUMENT


def test_business_plan_wording_stays_off_document():
    for message in ("事業計画書を作って", "企画書を作って"):
        assert detect_creation_intent(message).kind is not CreationKind.DOCUMENT


def test_document_howto_stays_a_question():
    assert not detect_creation_intent("議事録の作り方を教えて").is_creation
