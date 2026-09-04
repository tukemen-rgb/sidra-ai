"""C-1220: a jump-game request must reach the platformer, not fishing.

``PLATFORMER_WORDS`` held only the compound 「ジャンプアクション」, so
「猫がジャンプするゲーム」 detected no genre and fell to the default fishing
template with no substitution notice. The bare jump cues now route to the
platformer, while a shooter/puzzle that only mentions a jump keeps its own
route (platformer is matched after them).
"""

from __future__ import annotations

import tempfile

from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.games import choose_template, detect_genre
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.jump_routes_to_platformer import evaluate_jump_routes_to_platformer


def test_jump_routes_eval_passes():
    result = evaluate_jump_routes_to_platformer()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_bare_jump_requests_reach_platformer():
    for request in ("猫がジャンプするゲームを作って", "ジャンプゲーム", "跳ねて進む", "穴を飛び越える"):
        assert choose_template(request) == "platformer", request
        g = detect_genre(request)
        assert g is not None and g.template == "platformer", request


def test_jump_as_scenery_keeps_the_named_genre():
    assert choose_template("ジャンプで敵を撃つシューティング") == "shooter"
    assert choose_template("ジャンプしながら解くパズル") == "puzzle"
    # Named fishing/catch outrank the bare jump verb (the doctrine the
    # earlier branches follow), so C-1220's cues do not steal them.
    assert choose_template("魚が跳ねる釣りゲーム") == "fishing"
    assert choose_template("跳ねる的をキャッチするゲーム") == "catch"


def test_jump_request_builds_platformer_without_substitution():
    request = "猫がジャンプするゲームを作って"
    with tempfile.TemporaryDirectory() as tmp:
        outcome = build_game_generator(tmp)(request, detect_creation_intent(request))
    assert outcome.details.get("built_template") == "platformer"
    assert not outcome.details.get("genre_substituted")
