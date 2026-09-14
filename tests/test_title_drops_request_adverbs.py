"""C-1829: a title names the thing asked for, not the sentence that asked.

Before this, every title builder cut the request at its making verb, so a word
between the artifact noun and that verb stayed - and stopped the end-anchored
kind strip too. 47 of 48 titles across six generators carried the request's
grammar.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.gifs import generate_gif
from sidra_ai.creation.projects import _title_from as project_title
from sidra_ai.creation.vocabulary import drop_request_adverbs
from sidra_ai.evals.title_drops_request_adverbs import (
    ADVERBS,
    SHAPES,
    evaluate_title_drops_request_adverbs,
)


def test_title_adverb_eval_passes():
    result = evaluate_title_drops_request_adverbs()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize("adverb", ADVERBS)
def test_a_game_titles_the_subject_not_the_adverb(adverb):
    shape = SHAPES["game"][0]
    assert generate_game(shape.format(adverb)).title == "猫"


@pytest.mark.parametrize("adverb", ADVERBS)
def test_a_gif_titles_the_subject_not_the_adverb(adverb):
    shape = SHAPES["gif"][0]
    assert generate_gif(shape.format(adverb)).title == "魚"


def test_the_production_drops_the_leftover_particle():
    # Removing 「一式」 left a space, so the anchored particle strip matched
    # nothing and 「レースゲームを」 named six files.
    assert project_title("レースゲームを企画から一式で作って") == "レースゲーム"
    assert project_title("忍者のゲームを企画から一式で作って") == "忍者のゲーム"


def test_an_ordinary_request_is_untouched():
    assert generate_game("猫のゲームを作って").title == "猫"
    assert generate_gif("魚のGIFを作って").title == "魚"


def test_the_helper_only_reads_the_tail():
    assert drop_request_adverbs("猫のゲームを今すぐ") == "猫のゲーム"
    assert drop_request_adverbs("今すぐ帰りたい人のゲーム") == "今すぐ帰りたい人のゲーム"
    assert drop_request_adverbs("猫のゲーム") == "猫のゲーム"


def test_a_word_about_the_artifact_is_not_an_adverb():
    # 「ざっくりした」 says what the art should look like; dropping it would
    # quote less than was asked for.
    assert "ざっくり" in drop_request_adverbs("ざっくりしたアート")
