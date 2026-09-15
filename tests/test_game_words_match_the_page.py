"""C-1855: the things a page draws can be asked for by name.

Found from §3. The lock-and-key structure itself was sound - the charm's
chamber has one opening, the key needs the cave cleared, the chest needs both
the key and the guardian - but naming that structure did not reach the
template that has it, and the refusal said the product could not draw a cave.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.adventure import ADVENTURE_WORDS
from sidra_ai.creation.games import choose_template, generate_game
from sidra_ai.evals.game_words_match_the_page import (
    NOT_OURS,
    ON_THE_PAGE,
    PAGE_REQUESTS,
    SETTLED,
    evaluate_game_words_match_the_page,
)


def test_game_words_eval_passes():
    result = evaluate_game_words_match_the_page()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


@pytest.mark.parametrize("request_text,template", PAGE_REQUESTS)
def test_naming_what_the_page_holds_reaches_it(request_text, template):
    assert choose_template(request_text) == template


@pytest.mark.parametrize("request_text", NOT_OURS)
def test_a_genre_this_product_lacks_is_still_not_claimed(request_text):
    """The same lie inverted, and the reason 「鍵」 is not in the table alone.

    「鍵盤」 is an instrument; 「脱出」 and 「RPG」 are genres nothing here builds.
    Routing them to the adventure would trade a false 「cannot」 for a false
    「can」, which is the trade C-1121 already refused.
    """

    assert choose_template(request_text) not in ("adventure", "puzzle")


@pytest.mark.parametrize("request_text,template", SETTLED)
def test_the_routing_that_already_worked_did_not_move(request_text, template):
    assert choose_template(request_text) == template


def test_the_offered_words_are_on_the_page():
    """What the table offers and what the generator draws, in one assertion."""

    html = generate_game("洞窟を探検するゲームを作って").html
    for word in ON_THE_PAGE:
        assert word in html, word


def test_the_genre_names_were_kept():
    """Adding the page's own words did not replace the names people also use."""

    for word in ("ゼルダ", "冒険", "ダンジョン", "adventure", "zelda"):
        assert word in ADVENTURE_WORDS
