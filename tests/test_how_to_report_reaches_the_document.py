"""C-1533: 「作り方」 vetoed a request that named both the artifact and the verb.

「ラーメンの作り方のレポートを書いて」 came back as Q&A excerpts, while
「ラーメンのレポートを書いて」 - the same request with a narrower subject -
built the document. The marker is not wrong to exist: this module's own
docstring rests on 「ゲームの作り方を教えて」 staying a question, and it must.

The rule the file already states is what tells them apart. Question markers
win over an earlier making-verb *because Japanese puts the operative verb
last*. Read the other way, that says a marker with the artifact's own noun
after it is not the operative ending - it is part of what the artifact is
about. 「作り方のレポート」 is a report about a method; 「作り方を教えて」 ends
on the asking.

Both directions are here, and the second half is the load-bearing one: a
patch that simply dropped 作り方 from the marker list would pass every case
in the first group and turn every how-to question into a generator request.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import detect_creation_intent


@pytest.mark.parametrize(
    "message",
    [
        # The filed case: a subject noun, then the marker, then the artifact.
        "ラーメンの作り方のレポートを書いて",
        "カレーの作り方のレポートを書いて",
        # No subject noun at all - the marker is the whole subject.
        "作り方のレポートを書いて",
        # A different artifact word behind a different connective.
        "ラーメンの作り方について記事を書いて",
        # The artifact word appears twice, and the head noun is the last one:
        # a report *about* making games is a document, not a game.
        "ゲームの作り方のレポートを書いて",
        # The *same* artifact word on both sides of the marker. These are what
        # make the rule's "last occurrence" load-bearing: reading the first
        # one puts the artifact before the marker and vetoes a plain request.
        "レポートの作り方のレポートを書いて",
    ],
)
def test_a_how_to_report_reaches_the_document_generator(message: str) -> None:
    intent = detect_creation_intent(message)

    assert intent.is_creation, f"{message} was not read as a request at all"
    assert intent.kind.value == "document", f"{message} -> {intent.kind.value}"


@pytest.mark.parametrize(
    "message",
    [
        # The module docstring's own case. Nothing follows 教えて.
        "ゲームの作り方を教えて",
        "ラーメンの作り方を教えて",
        # The artifact comes first here, so it is what the question is about.
        "レポートの作り方を教えて",
        # Politeness does not turn an explanation question into a request.
        "ゲームの作り方を教えてもらえますか",
        "レポートの作り方を教えてください",
        # The case the whole veto exists for, and the only one in this file
        # that 作り方 holds up by itself - every other line here also carries
        # 教えて, so a patch that simply deleted 作り方 from the marker list
        # would pass all of them. Found by diffing classifications under each
        # deliberate break rather than by thinking of it: "write out how to
        # make a game" must not build a game.
        "ゲームの作り方を書いて",
        "資料の作り方を書いて",
        # English puts its interrogative FIRST, so the artifact is always
        # after the marker and "the artifact comes last" would route every
        # how-to question to a generator. Caught by the full suite, not by
        # anything written here, which is why the rule asks whether the
        # marker is a noun before it asks where it sits.
        "how do I build a game",
        "how can I make a report",
        "why is a game slow",
    ],
)
def test_a_how_to_question_is_still_a_question(message: str) -> None:
    intent = detect_creation_intent(message)

    assert not intent.is_creation, (
        f"{message} -> {intent.kind.value}: a how-to question became a request"
    )


def test_the_last_occurrence_of_the_artifact_is_the_one_that_counts() -> None:
    """「資料」 is a deck word, so this one proves the rule on a different kind
    as well as on a different position: reading the *first* 資料 puts the
    artifact before the marker and vetoes a plainly-phrased request."""

    intent = detect_creation_intent("資料の作り方の資料を作って")

    assert intent.is_creation
    assert intent.kind.value == "deck"


def test_the_narrower_request_still_works() -> None:
    """The comparison that made the defect visible: the same sentence without
    the marker always routed, which is why this read as a hole rather than a
    policy."""

    assert detect_creation_intent("ラーメンのレポートを書いて").kind.value == "document"


def test_a_polite_making_request_is_untouched() -> None:
    """C-1454's exemption is not what is being changed here."""

    assert detect_creation_intent("資料を作成いただけますか").kind.value == "deck"
