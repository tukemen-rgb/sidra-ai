"""C-1537: the three ask-backs answer in the language they were asked in.

The eval reads the real service, so these tests read it too rather than
asserting on strings the eval happens to build.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.api.service import SidraService
from sidra_ai.evals.ask_back_matches_the_language_asked import (
    evaluate_ask_back_matches_the_language_asked,
)

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")


@pytest.fixture(scope="module")
def service() -> SidraService:
    return SidraService()


def test_all_three_ask_backs_are_right() -> None:
    result = evaluate_ask_back_matches_the_language_asked()
    assert result.japanese_held, result.failures
    assert result.sides_right == result.sides_total == 3, result.failures


@pytest.mark.parametrize(
    "message, refusal",
    [("racing game", "ambiguous"), ("surprise me", "unnamed")],
)
def test_an_english_ask_gets_an_english_ask_back(
    service: SidraService, message: str, refusal: str
) -> None:
    reply = service.chat(message)
    assert reply["refusal"] == refusal
    assert not _JAPANESE.search(reply["answer"]), reply["answer"]


@pytest.mark.parametrize(
    "message, refusal, keeps",
    [
        ("パズル", "ambiguous", "リポジトリから探しますか"),
        ("なにか作って", "unnamed", "何をお作りしましょうか"),
    ],
)
def test_a_japanese_ask_keeps_its_own_ask_back(
    service: SidraService, message: str, refusal: str, keeps: str
) -> None:
    # The guard direction. An English reply bought by breaking this one is a
    # regression, which is why the eval scores 0 when it moves.
    reply = service.chat(message)
    assert reply["refusal"] == refusal
    assert keeps in reply["answer"]


@pytest.mark.parametrize("message", ["", "   ", "...", "？？？"])
def test_a_message_with_no_language_is_answered_in_japanese(
    service: SidraService, message: str
) -> None:
    # C-1248, deliberately: there is no language in the input to match, and
    # this product's readers are Japanese. The filing counted this as the
    # third defect; measuring said it is the stated default. Pinned so that
    # finishing C-1537 cannot quietly undo C-1248.
    reply = service.chat(message)
    assert reply["refusal"] == "empty"
    assert _JAPANESE.search(reply["answer"]), reply["answer"]


def test_the_english_ask_back_still_names_what_it_can_make(
    service: SidraService,
) -> None:
    # The escape the first version of the eval left open: an English sentence
    # that dropped the list would pass "is it English?" while saying less than
    # the Japanese one. Counted in the sentence, not in the metadata - the
    # metadata carries Japanese labels and is built before the sentence.
    from sidra_ai.api.service import _KIND_LABELS_EN

    for message in ("racing game", "surprise me"):
        answer = service.chat(message)["answer"].lower()
        named = [label for label in _KIND_LABELS_EN.values() if label.lower() in answer]
        assert len(named) >= 2, (message, answer)
