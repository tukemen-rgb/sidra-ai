"""C-1240: quiz/mahjong/card/board decline as genres, not drawn subjects.

They were missing from GENRES, so detect_genre returned None and they fell to
the subject path (「『クイズ』の題材を描く型はまだ無い」), which never lists what
can be built. Named as unsupported genres now, they decline with the buildable
list; real subjects and supported genres are unchanged.
"""

from __future__ import annotations

import tempfile

from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.games import detect_genre
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.unsupported_genre_not_subject import (
    evaluate_unsupported_genre_not_subject,
)


def _summary(request: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        return build_game_generator(tmp)(request, detect_creation_intent(request)).summary


def test_unsupported_genre_not_subject_eval_passes():
    result = evaluate_unsupported_genre_not_subject()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_quiz_and_mahjong_decline_as_genres_with_list():
    for request in ("クイズゲームを作って", "麻雀ゲームを作って"):
        s = _summary(request)
        assert "型はまだ作れない" in s
        assert "いま作れるのは" in s
        assert "題材を描く型はまだ無い" not in s


def test_new_genres_are_recognised_and_unsupported():
    for request in ("クイズゲームを作って", "麻雀ゲームを作って", "カードゲームを作って"):
        g = detect_genre(request)
        assert g is not None and not g.supported


def test_real_subject_and_supported_genre_unchanged():
    assert "題材を描く型はまだ無い" in _summary("猫のゲームを作って")
    assert "型はまだ作れない" not in _summary("シューティングを作って")
