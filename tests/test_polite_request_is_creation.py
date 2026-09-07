"""C-1454: a politely-phrased request to make something routes to a generator.

The courtesy veto ('ますか') used to swallow polite requests
('資料を作成いただけますか'), answering them as questions. The detector now
recognises a making stem plus a benefactive/honorific auxiliary as a request,
while an explanation question ('作り方を教えて') still stays a question.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.evals.polite_request_is_creation import (
    evaluate_polite_request_is_creation,
)


def test_polite_request_eval_passes():
    result = evaluate_polite_request_is_creation()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 11


@pytest.mark.parametrize(
    "message,kind",
    [
        ("スライドを作ってもらえますか", CreationKind.DECK),
        ("スライドを作成いただけますか", CreationKind.DECK),
        ("レポートを書いてもらえますか", CreationKind.DOCUMENT),
        ("アートを描いてください", CreationKind.ART),
    ],
)
def test_polite_requests_route(message: str, kind: CreationKind):
    intent = detect_creation_intent(message)
    assert intent.routes
    assert intent.kind is kind


@pytest.mark.parametrize(
    "message",
    [
        "スライドの作り方を教えてもらえますか",
        "デッキはどうやって作りますか",
        "スライドの作成方法を教えて",
        "資料を作ってますか",
    ],
)
def test_questions_stay_questions(message: str):
    assert not detect_creation_intent(message).is_creation
