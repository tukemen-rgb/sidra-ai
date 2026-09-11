"""A genre word on its own is not a request, and not a question either.

Measured 2026-09-11 (C-1527, the sixth review): one request written
seventeen ways reached a generator twelve times. Four of the five misses
were phrasings with a real ask in them - 「I want a…」, 「…が欲しい」 - and
they were fixed. The fifth is 「racing game」, and it is different in kind:
that is what someone types to be handed a racing game *and* what they type
to go looking for one, and nothing in the two words tells them apart.

Both available answers are therefore guesses. Building it delivers a page
nobody asked for; answering it as a question leaves the gap the review
measured. The honest answer is to ask which, in the shape C-1515 uses for
a message with no question in it at all (C-1670).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.api.app import create_app  # noqa: E402
from sidra_ai.creation.intent import detect_creation_intent  # noqa: E402

NO_EVIDENCE = "十分な根拠がありません"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize(
    "message",
    ["racing game", "a racing game", "レースゲーム", "パズル", "puzzle game"],
)
def test_a_bare_genre_is_asked_about_rather_than_guessed(
    client: TestClient, message: str
) -> None:
    body = client.post("/v1/chat", json={"message": message}).json()

    assert body["refusal"] == "ambiguous"
    assert body["citations"] == []
    assert NO_EVIDENCE not in body["answer"], (
        "naming a genre is not being told the corpus lacks your topic"
    )
    # Both readings offered and neither chosen. Asserted on the two verbs
    # and the disjunction rather than the whole sentence, so the copy can be
    # reworded without this becoming a spelling test - but 「それとも」 is
    # load-bearing: without it the same two verbs could appear in a sentence
    # that had already picked one.
    assert "作り" in body["answer"], "the answer must offer to build it"
    assert "探し" in body["answer"], "the answer must offer to search for it"
    assert "それとも" in body["answer"], "the answer must not pick one of them"
    assert body["creation"]["outcome"]["asked_back"] is True


@pytest.mark.parametrize(
    "message",
    [
        # A real question that happens to contain an artifact word. Turning
        # one of these into a prompt would take the question path away from
        # someone who wanted it - the failure the detector exists to avoid.
        "ゲーム業界の市場規模は",
        "SIDRA は取得した文書をどう扱いますか",
        "ゲームの作り方を教えて",
        "what is a pitch deck",
    ],
)
def test_a_question_that_names_a_thing_is_still_a_question(message: str) -> None:
    intent = detect_creation_intent(message)

    assert intent.confidence != "ambiguous"


@pytest.mark.parametrize(
    "message",
    ["レースゲームを作って", "I want a racing game", "make me a fishing game"],
)
def test_a_request_with_an_ask_in_it_still_routes(message: str) -> None:
    """The other direction: asking back must not become the new default.

    These carry a making-verb or a desire, so there is evidence and nothing
    to ask about. If they started asking back, every one of C-1527's fixes
    would have been undone by this one.
    """

    intent = detect_creation_intent(message)

    assert intent.routes
    assert intent.confidence == "strong"


def test_asking_which_is_cheaper_than_answering(client: TestClient) -> None:
    """It must not retrieve first. The query is a noun; what to do with it
    depends on an answer nobody has given yet."""

    body = client.post("/v1/chat", json={"message": "racing game"}).json()

    assert body["citations"] == []
    assert "確認した質問" not in body["answer"]
