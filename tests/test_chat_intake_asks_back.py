"""C-1530: decorating a word the tables already know must not lose it.

The seventh review put sixteen ways of asking for a game through
``/v1/chat``. Ten came back with the Q&A boilerplate - 「現時点では十分な
根拠がありません」 - which tells the operator their topic is missing from the
corpus. It is not a claim about the corpus at all; nobody asked it anything.

The decisive pair was 「パズル」 against 「パズルっぽいの」. The first asked
which; the second fell through, on four characters. Measuring it showed the
filed cause was half right: the artifact table is *already* matched by
substring - 「レース」 is found inside 「レースみたいなの」 - and what is exact
is the test that follows it, which requires the message to reduce to nothing
once the artifact is removed. Each of the five left exactly one word behind:
ッポイ / ミタイナ / ヤツ / pls / gimme.

So this is three fixes, not one, and each input gets the one its grammar
asks for:

* a genre under a vagueness wrapper is a bare name, and is asked about;
* 「puzzle pls」 and 「gimme a racing game」 are requests, and are built -
  「puzzle please」 and 「パズルをください」 already were, so these two were
  an abbreviation and a missing imperative rather than a new idea;
* a message that asks for a thing and names none is answered with what can
  be made.

The last one is where the cost is. An early draft read the indefinite
pronoun alone as a request, and answered 「何かエラーが出てる」, "something is
broken" and "anything in the logs" with an offer to build something - the
failure this module exists to avoid, pointed the other way. Those are here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.creation.intent import detect_creation_intent

NO_EVIDENCE = "十分な根拠がありません"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _ask(client: TestClient, message: str) -> dict:
    return client.post("/v1/chat", json={"message": message}).json()


# ----------------------------------------------- a genre, loosely named


@pytest.mark.parametrize(
    "message", ["パズルっぽいの", "レースみたいなの", "釣りのやつ", "ゲームみたいなやつ"]
)
def test_a_genre_under_a_vagueness_wrapper_is_still_a_bare_genre(
    client: TestClient, message: str
) -> None:
    body = _ask(client, message)

    assert body["refusal"] == "ambiguous", body["answer"][:80]
    assert NO_EVIDENCE not in body["answer"]
    assert body["creation"]["outcome"]["asked_back"] is True


# --------------------------------------- the request spelled informally


@pytest.mark.parametrize(
    "message,plain",
    [
        ("puzzle pls", "puzzle please"),
        ("gimme a racing game", "give me a racing game"),
    ],
)
def test_the_informal_request_routes_where_the_plain_one_does(
    message: str, plain: str
) -> None:
    """Not a new rule: the same sentence written out already routed.

    Asserted against the plain spelling rather than a hard-coded ``True`` so
    this cannot pass by both of them breaking.
    """

    assert detect_creation_intent(plain).routes, "the plain spelling regressed"
    assert detect_creation_intent(message).routes
    assert detect_creation_intent(message).kind is detect_creation_intent(plain).kind


# ------------------------------------------- asked for something, named none


@pytest.mark.parametrize(
    "message",
    [
        "ひまだからなにか遊べるもの",
        "暇つぶしになるもの頼む",
        "something fun to play",
        "anything for my kid",
        "surprise me",
    ],
)
def test_a_want_with_no_subject_is_answered_with_what_can_be_made(
    client: TestClient, message: str
) -> None:
    body = _ask(client, message)

    assert body["refusal"] == "unnamed", body["answer"][:80]
    assert NO_EVIDENCE not in body["answer"], (
        "asking for something is not being told the corpus lacks your topic"
    )
    assert body["citations"] == []
    assert body["creation"]["outcome"]["asked_back"] is True
    # The point of the answer is the list: without it this is the boilerplate
    # with better manners.
    offered = body["creation"]["outcome"]["offered"]
    assert offered, "nothing was offered to choose from"
    assert all(label in body["answer"] for label in offered)


# ------------------------------------------------------- the other direction


@pytest.mark.parametrize(
    "message",
    [
        # The indefinite pronoun in its ordinary use: a report about this
        # repository, not a request for a thing.
        "何かエラーが出てる",
        "なにか問題がある",
        "なんかおかしい",
        "something is broken",
        "something went wrong",
        "anything in the logs",
        "anything that broke the build",
        # A ください with a subject: asking to be shown a file, not to be
        # given a thing.
        "READMEを見せてください",
        "設定ファイルのやつを教えて",
        # The case the subtraction test has always had to keep getting
        # right: a genre word inside a question.
        "ゲーム業界の市場規模",
        "ゲームエンジンの選び方を教えて",
    ],
)
def test_a_question_about_the_repository_is_still_a_question(message: str) -> None:
    intent = detect_creation_intent(message)

    assert intent.confidence != "unnamed", (
        f"{message!r} was read as a request to make something"
    )
    assert not intent.routes


def test_naming_the_genre_inside_a_question_still_reaches_retrieval(
    client: TestClient,
) -> None:
    """The load-bearing one, through the whole path rather than the detector.

    ``_only_names_the_artifact`` subtracts the vagueness wrappers now, so
    this is the case that proves the subtraction still leaves a subject
    behind: 「ゲーム業界の市場規模」 keeps 業界市場規模 and stays a question.
    """

    body = _ask(client, "ゲーム業界の市場規模")
    outcome = (body.get("creation") or {}).get("outcome") or {}

    assert body["refusal"] not in ("ambiguous", "unnamed"), body["answer"][:80]
    assert not outcome.get("asked_back"), "a question was answered with a question"
