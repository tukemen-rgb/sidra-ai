"""A blank line is not a question, and must not be answered as one.

Measured 2026-09-09 through the real API: ``chat("   ")`` returned
「現時点では十分な根拠がありません。資料を索引した範囲では、この質問へ
答えられる内容が見つかりませんでした」 with 「確認した質問: 」 and nothing
after it. That sentence is a claim about a search - it tells the operator
their topic is not in the corpus - and no search with a query ever happened.

The empty string used to be a separate case - the HTTP schema pinned
``min_length=1``, so ``""`` was a 422 before any of this ran while whitespace
reached the ask-back. That split is exactly what C-1536 removed: an empty
message is a question the service answers with the ask-back, not a validation
error, so ``""`` now behaves like whitespace and is checked alongside it. The
``max_length`` cap stays (an over-long post is a genuine 422).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.api.app import create_app  # noqa: E402

NO_EVIDENCE = "十分な根拠がありません"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize("message", ["", "   ", "\t\n ", "　"])
def test_whitespace_is_asked_back_rather_than_answered(
    client: TestClient, message: str
) -> None:
    """Empty and whitespace alike, including the ideographic space a Japanese
    keyboard produces (the empty string joined this set with C-1536)."""

    body = client.post("/v1/chat", json={"message": message}).json()

    assert body["refused"] is True
    assert body["refusal"] == "empty"
    assert body["citations"] == []
    assert NO_EVIDENCE not in body["answer"], (
        "a blank line must not be told that the corpus lacks its topic"
    )
    assert "何について" in body["answer"], "the answer must ask for a question"


def test_the_empty_string_reaches_the_ask_back_not_a_bare_422(
    client: TestClient,
) -> None:
    """C-1536: an empty message is answered by the service (200), not rejected
    at the schema (422); the length cap still rejects an over-long message."""

    resp = client.post("/v1/chat", json={"message": ""})
    assert resp.status_code == 200
    assert resp.json()["refusal"] == "empty"
    assert client.post("/v1/chat", json={"message": "あ" * 32_001}).status_code == 422


def test_a_real_question_is_untouched(client: TestClient) -> None:
    """The half that keeps the fix from being 'refuse more'.

    A question the corpus cannot answer must still get the honest
    no-evidence sentence - that sentence is correct there, because a search
    with a real query did happen and found nothing. (The example was once
    「こんにちは」, but a bare greeting is not a question and now gets its own
    friendly reply - C-1796 - so a genuine question stands in for it here.)
    """

    body = client.post("/v1/chat", json={"message": "火星の天気を教えて"}).json()

    assert body["refused"] is False
    assert NO_EVIDENCE in body["answer"]


def test_whitespace_never_reaches_retrieval(client: TestClient) -> None:
    """Asking back must be cheaper than answering, not just differently worded.

    Pinned through the response rather than by patching: a run that had
    searched would carry the question back in 「確認した質問:」.
    """

    body = client.post("/v1/chat", json={"message": "   "}).json()

    assert "確認した質問" not in body["answer"]
