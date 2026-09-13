"""C-1773: 「〜をレポートにして」 named the artifact and reached nothing.

Split out of C-1533, which fixed the 作り方 veto and left this one standing:
「ラーメンの作り方をレポートにして」 came back with ``confidence='none'`` and no
evidence at all - not vetoed, simply never read as a request. 「にして」 is not
a making verb; it is 「する」 with a target, so no verb table can hold it.

The obvious change was tried and measured first, because 「にして」 is also the
reviser's idiom. Adding it to ``_MAKE_VERBS`` and diffing against ten revision
phrasings:

* 「タイトルを『夜のレース』にして」 became a request to **build a racing game**
  (「レース」 is a game word), and
* the two revisions that carry a referent - 「さっきのゲームのタイトルを『夜』に
  して」 and 「そのゲームを紙のテーマにして」 - stopped being read as revisions at
  all, because the reviser asks the creation detector first.

What separates them needs no word list: a revision puts a **value** before
「にして」 (紙, 青, hard, 『夜』, テーマ) and a creation request puts the
**artifact itself**. So the rule is adjacency, and both halves are checked
here - a patch that widened the verb table would pass every case in the first
group and quietly break the reviser.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.revise import detect_revision_intent


@pytest.mark.parametrize(
    "message,kind",
    [
        ("ラーメンの作り方をレポートにして", "document"),
        ("ラーメンのレポートにして", "document"),
        ("この内容をレポートにして", "document"),
        ("議事録にして", "document"),
        ("ラーメンの作り方を記事にして", "document"),
        # A different kind, so the rule is not fitted to one word.
        ("さっきの話を資料にして", "deck"),
        # Politeness rides along, as it does for every other request form.
        ("この内容をレポートにしてください", "document"),
    ],
)
def test_turning_something_into_an_artifact_is_a_request(message: str, kind: str) -> None:
    intent = detect_creation_intent(message)

    assert intent.is_creation, f"{message} was not read as a request at all"
    assert intent.kind.value == kind, f"{message} -> {intent.kind.value}"


@pytest.mark.parametrize(
    "message",
    [
        # The one the naive change turned into "build a racing game".
        "タイトルを『夜のレース』にして",
        "テーマを紙にして",
        "色を青にして",
        "差し色を赤にして",
        "難易度をhardにして",
        # Mentioning the artifact is not asking for one: the value sits
        # between it and 「にして」.
        "そのゲームを紙のテーマにして",
        "さっきのゲームのタイトルを『夜』にして",
    ],
)
def test_changing_a_value_is_not_a_request_to_build(message: str) -> None:
    assert not detect_creation_intent(message).is_creation, (
        f"{message} was read as a creation request; the reviser loses it"
    )


@pytest.mark.parametrize(
    "message,axis",
    [
        ("さっきのゲームのタイトルを『夜』にして", "title"),
        ("そのゲームを紙のテーマにして", "theme"),
    ],
)
def test_the_reviser_still_sees_the_revisions_it_saw_before(message: str, axis: str) -> None:
    """The half the naive change broke, and the half a routing metric cannot
    see: ``detect_revision_intent`` asks the creation detector first, so a
    widened verb table silently emptied it."""

    intent = detect_revision_intent(message)

    assert intent.is_revision, f"{message} stopped being a revision"
    assert axis in intent.adjustments


def test_the_artifact_must_be_adjacent() -> None:
    """The rule itself, on a sentence that names an artifact *and* changes a
    value. Only the adjacency tells them apart."""

    assert detect_creation_intent("この資料をレポートにして").is_creation
    assert not detect_creation_intent("この資料のテーマを紙にして").is_creation


def test_the_evidence_is_a_literal_not_the_requester_s_words() -> None:
    """``_asks_for_artifact``'s contract, and the reason it returns a token.

    Evidence is echoed into logs and into the reply that asks the operator
    which of two readings was meant. A request form that reported the text
    it matched would put whatever was typed - a title, a name, a pasted
    line - into both. Every token here is a literal from this module.
    """

    intent = detect_creation_intent("『社外秘メモ』をレポートにして")

    assert intent.is_creation
    assert "turn_into_request" in intent.evidence
    for token in intent.evidence:
        assert "社外秘" not in token, f"the requester's words reached evidence: {token}"
        assert "『" not in token and "』" not in token
