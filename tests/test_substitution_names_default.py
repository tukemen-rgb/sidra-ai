"""C-1230: a genre substitution names the default, not a false "nearest".

「格闘ゲーム」「ノベルゲーム」「音ゲー」 all fell to the default fishing
template, yet the summary said 「いちばん近い『タイミング釣り』型」. The router
measures no nearness, so the wording now says 「代わりに既定の」 while still
naming the genre asked for and the template built.
"""

from __future__ import annotations

import tempfile

from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.substitution_names_default import (
    evaluate_substitution_names_default,
)


def _summary(request: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        return build_game_generator(tmp)(request, detect_creation_intent(request)).summary


def test_substitution_names_default_eval_passes():
    result = evaluate_substitution_names_default()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_unsupported_genres_say_default_not_nearest():
    for request, genre in (("格闘ゲームを作って", "対戦格闘"), ("音ゲーを作って", "リズム")):
        s = _summary(request)
        assert "いちばん近い" not in s
        assert "代わりに既定の" in s
        assert genre in s and "タイミング釣り" in s


def test_subject_substitution_says_default():
    s = _summary("猫のゲームを作って")
    assert "いちばん近い" not in s
    assert "代わりに既定の" in s
