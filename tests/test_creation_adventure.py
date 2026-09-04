"""The adventure template: the genre is buildable, the name is not takeable.

The directive was a video - an original top-down action-adventure made by
people who loved Minish Cap - plus 「ゼルダの伝説 不思議なぼうし作って」. So
the tests pin the two halves of that deal separately: the request routes and
produces a playable tile world (rooms, sword, key, chest, NPC), and the
trademark never survives onto the artifact, with the rename said out loud
rather than done silently.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import (
    TEMPLATES,
    choose_template,
    generate_game,
    validate_game_html,
)
from sidra_ai.creation.intent import CreationKind, detect_creation_intent


def test_the_directive_request_routes_and_plays() -> None:
    """「ゼルダの伝説 不思議なぼうしつくって」 - no word ゲーム anywhere."""

    intent = detect_creation_intent("ゼルダの伝説 不思議なぼうしつくって")
    assert intent.kind is CreationKind.GAME and intent.routes

    game = generate_game("ゼルダの伝説 不思議なぼうしつくって")
    assert game.template == "adventure"
    verdict = validate_game_html(game.html)
    assert verdict["playable"], verdict["failures"]


@pytest.mark.parametrize(
    "request_text",
    ["冒険ゲームを作って", "ダンジョン探索ゲームを作って", "adventure game を作って"],
)
def test_genre_words_reach_the_adventure_template(request_text: str) -> None:
    assert choose_template(request_text) == "adventure"


def test_existing_templates_are_not_stolen() -> None:
    assert choose_template("釣りゲームを作って") == "fishing"
    assert choose_template("キャッチゲームを作って") == "catch"


def test_the_trademark_never_reaches_the_artifact() -> None:
    """The genre is ours to build; the name is someone's. Openly swapped."""

    game = generate_game("ゼルダの伝説 不思議なぼうしを作って")

    assert "ゼルダ" not in game.title
    assert game.title == TEMPLATES["adventure"].default_title
    assert "オリジナル版" in game.tagline
    # The page's visible copy carries neither the mark nor a claim to it.
    assert "ゼルダ" not in game.html


def test_an_original_title_is_kept_untouched() -> None:
    """The guard fires on trademarks, not on the operator's own words."""

    game = generate_game("ほら穴の冒険を作って")
    assert game.title == "ほら穴の冒険"
    assert "オリジナル版" not in game.tagline


def test_the_world_is_seeded_by_the_request() -> None:
    same_a = generate_game("森の冒険を作って")
    same_b = generate_game("森の冒険を作って")
    other = generate_game("湖の冒険を作って")

    assert same_a.html == same_b.html
    assert same_a.html != other.html
    # The seed actually reaches the script, not only the title.
    assert "SEED_TOKEN" not in same_a.html


def test_difficulty_changes_the_numbers_not_the_wording() -> None:
    normal = generate_game("冒険ゲームを作って")
    hard = generate_game("難しい冒険ゲームを作って")

    assert normal.html != hard.html
    # Spelled through the tuning panel since C-1113: the generator still
    # picks the number, and it is still the number the page starts on -
    # tuneNum returns its fallback unless this browser saved something.
    assert "ESPEED=adaptSpeed(tuneNum('speed',1.2))" in hard.html
    assert "ESPEED=adaptSpeed(tuneNum('speed',0.8))" in normal.html


def test_the_page_keeps_every_house_rule() -> None:
    game = generate_game("冒険ゲームを作って")

    assert "http://" not in game.html and "https://" not in game.html
    # The animation preamble is present, so torches freeze under reduced
    # motion instead of flickering at someone who asked them not to.
    assert "prefers-reduced-motion" in game.html


def test_the_world_has_the_promised_shape() -> None:
    """Three rooms, a sword, a key, a chest, an NPC line - the genre's spine."""

    html = generate_game("冒険ゲームを作って").html
    for marker in ("森のはずれ", "ひかり苔の洞窟", "風の祭壇", "鍵を手に入れた", "swing", "宝箱"):
        assert marker in html, marker


def test_a_zelda_question_is_still_a_question() -> None:
    assert not detect_creation_intent("ゼルダの伝説とは").is_creation
    assert not detect_creation_intent("ゼルダの伝説の作り方を教えて").is_creation


def test_the_map_reads_by_form_not_colour_alone() -> None:
    """Knowledge base §4: walls get edge highlights, doors get a chevron,
    and the pond is carved for real - the water tile shipped as dead code
    once, and 'defined' is not 'placed'."""

    html = generate_game("冒険ゲームを作って").html

    assert "pond(forest)" in html
    assert "closePath" in html  # the door chevron path
    assert "#ffffff2e" in html  # wall top highlight (form, not hue)
    assert "BORDER_TOKEN" not in html  # the wall colour token was substituted


def test_entering_a_room_cannot_hurt_you_before_you_can_see_it() -> None:
    """C-1022 (3): enemies spawned beside the door with a 4-tile chase radius
    bit the hero on entry. Both halves of the fix are pinned: spawns keep
    distance from the entrance, and the transition grants mercy frames."""

    html = generate_game("冒険ゲームを作って").html

    assert "Math.abs(x-1)+Math.abs(y-4)<5" in html
    assert "Math.max(hero.inv,45)" in html


def test_the_sword_hits_where_it_is_drawn() -> None:
    """C-1022 (4): the drawn arc and the hitbox share their radius."""

    html = generate_game("冒険ゲームを作って").html
    assert "cx.arc(hero.x,hero.y,22," in html
    assert "<22){en.alive=false" in html


def _fought() -> dict:
    import json as _json
    import re
    import shutil as _shutil
    import subprocess as _subprocess

    import pytest as _pytest

    from sidra_ai.creation.adventure import guard_probe

    if _shutil.which("node") is None:  # pragma: no cover - environment guard
        _pytest.skip("node is required to drive the page")
    page = generate_game("迷宮を冒険するゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = _subprocess.run(
        ["node", "-"],
        input=guard_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return _json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_key_alone_does_not_open_the_chest():
    """§3: the boss stands behind the boss key. Fought, not grepped."""

    fought = _fought()

    assert fought["firstAlive"] is True
    assert fought["firstHp"] == fought["firstMax"] >= 4
    assert fought["lockedState"] == "play", "the chest refused a key over a live guardian"


def test_mashing_lands_one_blow():
    fought = _fought()

    assert fought["hpA"] == fought["hpB"] == fought["firstHp"] - 1


def test_the_guardian_speaks_the_boss_grammar_and_phase_two_reaccelerates():
    """§6 観察 2-3: wind-up then charge, and half health is the same fight faster."""

    fought = _fought()

    assert fought["sawWind"] and fought["sawCharge"]
    assert fought["p2"] is not None
    assert fought["p2"]["speed"] > fought["p1"]["speed"]
    assert fought["p2"]["wind"] < fought["p1"]["wind"]


def test_the_win_only_follows_the_fall():
    fought = _fought()

    assert fought["fallenAlive"] is False
    assert fought["finalState"] == "win"


def test_a_press_during_the_swing_fires_when_the_arm_is_free():
    """§12's attack side (C-1311), played: one queued blow, no ghosts."""

    import json as _json
    import re
    import shutil as _shutil
    import subprocess as _subprocess

    import pytest as _pytest

    from sidra_ai.creation.adventure import combo_probe

    if _shutil.which("node") is None:  # pragma: no cover - environment guard
        _pytest.skip("node is required to drive the page")
    page = generate_game("迷宮を冒険するゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = _subprocess.run(
        ["node", "-"],
        input=combo_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    seen = _json.loads(probe.stdout.strip().splitlines()[-1])

    assert seen["keptQueue"] is True
    assert seen["secondSwing"] >= 8, "the queued blow fired at the swing's end"
    assert seen["afterSingle"] == 0 and seen["ghostQueue"] is False


def _struck(request: str = "迷宮を冒険するゲームを作って") -> dict:
    """A fatal blow on a charm-bearer at one heart, then another."""

    import json as _json
    import re as _re
    import shutil as _shutil
    import subprocess as _subprocess

    import pytest as _pytest

    from sidra_ai.creation.adventure import charm_probe
    from sidra_ai.creation.games import generate_game as _generate

    if _shutil.which("node") is None:  # pragma: no cover - environment guard
        _pytest.skip("node is required to drive the page")
    page = _generate(request).html
    script = _re.search(r"<script>(.*?)</script>", page, _re.S)
    assert script is not None
    probe = _subprocess.run(
        ["node", "-"],
        input=charm_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return _json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_charm_takes_one_fatal_hit_and_shatters():
    """§3 (C-1323): the optional reward finally guards, exactly once."""

    struck = _struck()
    save = struck["afterSave"]

    assert save["state"] == "play" and save["hp"] == 1
    assert save["charm"] is False, "the shield does not reform"
    assert save["inv"] > 60, "the mercy outlasts a normal hit's"
    assert save["beats"] == 0, "no failure beat for a death that did not happen"


def test_the_second_fatal_hit_is_an_ordinary_death():
    struck = _struck()

    assert struck["afterDeath"]["state"] == "over"
    assert struck["afterDeath"]["beats"] == 1
