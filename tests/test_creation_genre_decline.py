"""C-1121: a genre we decline is declined in all three places.

「対戦格闘ゲームを作って」 was answered with a beam duel, no caveat, and a
page titled 「対戦格闘」 - the wrong template, no apology, and a name
claiming a genre this product does not build. The three layers had three
separate causes:

* ``DUEL_WORDS`` carries a bare 「対戦」, and the duel was tried before the
  fighting game in the genre table;
* ``choose_template`` was a second, hand-written ladder that did not know
  the genre had been declined - the same drift C-1120 fixed one level down;
* the title echoes the operator's own words, which claim nothing until
  those words name a genre that was just refused.
"""

from __future__ import annotations

import tempfile

import pytest

from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.games import (
    TEMPLATES,
    choose_template,
    detect_genre,
    generate_game,
)
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.vocabulary import GENRES

#: The three ways of naming the fighting game. They were three different
#: questions to the old table, which is the bug.
FIGHTER_ASKS = ("格闘ゲームを作って", "対戦格闘ゲームを作って", "格闘対戦を作って", "格ゲーを作って")

#: What must keep working: the beam duel is a genre this product *does*
#: build, and 「対戦」 is how people ask for it.
DUEL_ASKS = ("ビーム対戦を作って", "対戦ゲームを作って", "ドラゴンボールみたいなゲームを作って")


@pytest.fixture(scope="module")
def answer():
    directory = tempfile.mkdtemp()
    generate = build_game_generator(directory)
    return lambda ask: generate(ask, detect_creation_intent(ask))


@pytest.mark.parametrize("ask", FIGHTER_ASKS)
def test_every_way_of_asking_for_a_fighting_game_is_declined(ask):
    named = detect_genre(ask)
    assert named is not None and named.genre == "対戦格闘"
    assert not named.supported


@pytest.mark.parametrize("ask", FIGHTER_ASKS)
def test_the_summary_names_the_gap_and_the_substitute(ask, answer):
    outcome = answer(ask)
    assert outcome.details["genre_substituted"]
    assert "対戦格闘" in outcome.summary
    built = outcome.details["built_template"]
    assert TEMPLATES[built].default_title in outcome.summary


@pytest.mark.parametrize("ask", FIGHTER_ASKS)
def test_the_page_does_not_call_itself_a_genre_we_declined(ask):
    page = generate_game(ask)
    assert page.title == TEMPLATES[page.template].default_title
    # The words are not lost - they are still what the caveat is about.
    assert page.asked_title


@pytest.mark.parametrize("ask", DUEL_ASKS)
def test_the_beam_duel_still_answers_to_the_words_people_use(ask, answer):
    outcome = answer(ask)
    assert outcome.details["built_template"] == "duel"
    assert not outcome.details["genre_substituted"]


def test_routing_cannot_disagree_with_the_honesty_table():
    # The invariant, rather than a list of examples: whatever the table
    # declines lands on a template that exists, and the two answers agree.
    for genre, key, words in GENRES:
        if key in TEMPLATES:
            continue
        ask = f"{words[0]}ゲームを作って"
        named = detect_genre(ask)
        assert named is not None and not named.supported, ask
        built = choose_template(ask)
        assert built in TEMPLATES, ask
        assert generate_game(ask).template == built, ask


def test_a_buildable_genre_keeps_the_words_it_was_asked_in():
    # The fix must not turn every page into its default title: only a
    # decline loses the operator's wording.
    assert generate_game("ビーム対戦を作って").title == "ビーム対戦"
    assert generate_game("釣りゲームを作って").title == "釣り"
    assert generate_game("猫のゲームを作って").title == "猫"


def test_a_word_that_names_a_buildable_genre_too_is_not_declined():
    # 「格闘シューティング」 names a shooter, which we build. The decline
    # must not swallow requests that also name something buildable.
    assert generate_game("格闘シューティングを作って").template == "shooter"
