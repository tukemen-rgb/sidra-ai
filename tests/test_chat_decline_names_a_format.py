"""C-1719: do not decline a format that was never named.

「なんか作って」 was answered 「制作のご依頼と受け取りましたが、この形式は
作れません」. The sentence is about a format; the message named none, so it
reads to the operator as "the thing you asked for is unsupported" - a claim
about a request nobody made.

The decline is not the bug. 「Excelの表を作って」 and 「動画を作って」 name
formats this product has no generator for, and saying so in their own words
is what ``CreationKind.UNKNOWN`` promises - C-1261 was the opposite mistake,
answering a make request with retrieval boilerplate. So the fix has to split
the two, and the tests have to hold both halves: dropping the decline for
everybody would silence the false one and is the easy way to look fixed.

What splits them is the head of the object, not the sentence. 「子どもが喜ぶ
やつ」 has content words - 子ども, 喜ぶ - but they say who it is for and what
it does, never what it is; the noun being asked for is 「やつ」. 「Excelの表」
ends in 表 and has named one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.creation.intent import detect_creation_intent


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _outcome(client: TestClient, message: str) -> dict:
    body = client.post("/v1/chat", json={"message": message}).json()
    return ((body.get("creation") or {}).get("outcome") or {}), body


@pytest.mark.parametrize(
    "message",
    ["なんか作って", "子どもが喜ぶやつ用意して", "なにか作って", "便利なやつを作って",
     "make me something", "build anything"],
)
def test_a_request_that_names_no_format_is_asked_about(
    client: TestClient, message: str
) -> None:
    outcome, body = _outcome(client, message)

    assert not outcome.get("declined"), (
        "told a format cannot be made, having named none: " + body["answer"][:60]
    )
    assert outcome.get("asked_back") is True
    assert "この形式は作れません" not in body["answer"]


@pytest.mark.parametrize(
    "message",
    ["Excelの表を作って", "動画を作って", "アプリを作って", "曲を作って", "Webサイトを作って"],
)
def test_a_request_that_names_an_unbuildable_format_is_still_declined(
    client: TestClient, message: str
) -> None:
    """The half that a blanket fix would quietly remove."""

    outcome, body = _outcome(client, message)

    assert outcome.get("declined") is True, body["answer"][:60]
    assert "この形式は作れません" in body["answer"]
    assert outcome.get("offered"), "a decline with nothing offered is a dead end"


@pytest.mark.parametrize(
    "message", ["レースゲームを作って", "レポートを作って", "スライドを作って"]
)
def test_a_request_that_names_a_buildable_format_is_still_built(
    client: TestClient, message: str
) -> None:
    outcome, _ = _outcome(client, message)

    assert outcome.get("handled") is True


def test_the_head_of_the_object_is_what_decides(client: TestClient) -> None:
    """Two requests of the same shape, split on their last noun.

    Written as a pair rather than two asserts so the thing being claimed -
    that these two are treated differently - cannot pass by both of them
    landing in the same branch.
    """

    placeholder = detect_creation_intent("子どもが喜ぶやつ用意して")
    named = detect_creation_intent("子どもが喜ぶ動画を用意して")

    assert placeholder.confidence == "unnamed"
    assert named.confidence != "unnamed"
    assert placeholder.is_creation and named.is_creation, (
        "both are make requests; only what they asked for differs"
    )
