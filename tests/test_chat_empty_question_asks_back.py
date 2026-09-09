"""A blank line is not a question, and must not be answered as one.

Measured 2026-09-09 through the real API: ``chat("   ")`` returned
「現時点では十分な根拠がありません。資料を索引した範囲では、この質問へ
答えられる内容が見つかりませんでした」 with 「確認した質問: 」 and nothing
after it. That sentence is a claim about a search - it tells the operator
their topic is not in the corpus - and no search with a query ever happened.

The empty string is a separate case and was already handled: the HTTP schema
pins ``min_length=1``, so ``""`` is a 422 before any of this runs. Only
whitespace reaches the service, which is why the check lives there.
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


@pytest.mark.parametrize("message", ["   ", "\t\n ", "　"])
def test_whitespace_is_asked_back_rather_than_answered(
    client: TestClient, message: str
) -> None:
    """Including the ideographic space, which a Japanese keyboard produces."""

    body = client.post("/v1/chat", json={"message": message}).json()

    assert body["refused"] is True
    assert body["refusal"] == "empty"
    assert body["citations"] == []
    assert NO_EVIDENCE not in body["answer"], (
        "a blank line must not be told that the corpus lacks its topic"
    )
    assert "何について" in body["answer"], "the answer must ask for a question"


def test_the_empty_string_is_still_rejected_by_the_schema(
    client: TestClient,
) -> None:
    """The other half of the pair, pinned so the two cannot drift apart."""

    assert client.post("/v1/chat", json={"message": ""}).status_code == 422


def test_a_real_question_is_untouched(client: TestClient) -> None:
    """The half that keeps the fix from being 'refuse more'.

    A question the corpus cannot answer must still get the honest
    no-evidence sentence - that sentence is correct there, because a search
    with a real query did happen and found nothing.
    """

    body = client.post("/v1/chat", json={"message": "こんにちは"}).json()

    assert body["refused"] is False
    assert NO_EVIDENCE in body["answer"]


def test_whitespace_never_reaches_retrieval(client: TestClient) -> None:
    """Asking back must be cheaper than answering, not just differently worded.

    Pinned through the response rather than by patching: a run that had
    searched would carry the question back in 「確認した質問:」.
    """

    body = client.post("/v1/chat", json={"message": "   "}).json()

    assert "確認した質問" not in body["answer"]
