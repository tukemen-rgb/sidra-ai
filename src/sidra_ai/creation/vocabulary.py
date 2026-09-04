"""One list of what a game request can name, for everyone who asks.

C-1120: the genre table lived in ``games.py`` while ``intent.py`` kept a
third, hand-written list of game words. They drifted, and the drift showed
at the front door: 「横スクロールのジャンプアクションを作って」,
「レースを作って」, 「RPG を作って」 and 「ぷよぷよみたいなの」 were all
turned away as non-creation requests and answered with retrieval
boilerplate - even though ``choose_template`` knew perfectly well what to
build for three of them. A router that can build a thing and a detector
that will not admit the request is the worst of both.

So the vocabulary lives here, imported by both. This module deliberately
depends on nothing but the template modules that own their own words:
``games`` imports ``intent`` for ``fold_kana``, so anything shared has to
sit below both of them.

The table includes genres the product **cannot** build (rpg, fighter,
simulation, novel, rhythm). That is not an oversight - naming them is what
lets a request for one be declined in its own words instead of falling
through to the default template or, worse, to an answer about documents.
"""

from __future__ import annotations

from sidra_ai.creation.adventure import ADVENTURE_WORDS
from sidra_ai.creation.duel import DUEL_WORDS
from sidra_ai.creation.kaiju import KAIJU_WORDS
from sidra_ai.creation.marble import MARBLE_WORDS
from sidra_ai.creation.platformer import PLATFORMER_WORDS
from sidra_ai.creation.puzzle import PUZZLE_WORDS
from sidra_ai.creation.racing import RACING_WORDS
from sidra_ai.creation.shooter import SHOOTER_WORDS

#: The two templates with no module of their own keep their words here, so
#: every genre's vocabulary is reachable from one place.
FISHING_WORDS = ("釣り", "つり", "fishing", "魚")
CATCH_WORDS = ("キャッチ", "catch", "受け", "落ちもの", "避け")

#: Label, template key, words. Order is significant and is the routing
#: order: the first match wins, which is why 3D outranks every verb and a
#: buildable beam duel is tried before the fighting game we must decline.
GENRES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # First of all: 3D names a dimension none of the other nine can
    # draw, so it outranks every word describing what you do in it.
    ("3D コース", "marble", MARBLE_WORDS),
    # Then: a giant-boss request names the monster, and every other genre
    # word in the sentence ("撃つ", "冒険") is describing what you do to it.
    ("巨大ボス", "kaiju", KAIJU_WORDS),
    # These three used to hand-write their words while the template module
    # owned a longer list, which is the same drift one level down: 「ぷよぷよ」
    # routed to the puzzle and was still not recognised as a game request.
    ("アドベンチャー", "adventure", ADVENTURE_WORDS),
    ("シューティング", "shooter", SHOOTER_WORDS),
    ("パズル", "puzzle", PUZZLE_WORDS),
    # The template module owns the vocabulary, as with kaiju and the duel:
    # one list routes and one list answers, so they cannot drift.
    ("レース", "racing", RACING_WORDS),
    ("RPG", "rpg", ("rpg", "ロールプレイング", "ロープレ")),
    # Before 対戦格闘: a franchise-beam request is a duel we *can* build, and
    # first-match order is what keeps it from falling into the fighting-game
    # apology below.
    ("ビーム対戦", "duel", DUEL_WORDS),
    (
        "対戦格闘",
        "fighter",
        ("格闘", "fighting", "格ゲー"),
    ),
    (
        "シミュレーション",
        "simulation",
        ("シミュレーション", "simulation", "経営ゲーム"),
    ),
    ("ノベル", "novel", ("ノベルゲーム", "ノベル", "visual novel", "サウンドノベル")),
    ("リズム", "rhythm", ("リズムゲーム", "音ゲー", "rhythm")),
    # Falling blocks are not the match-clear board this product builds, so
    # this is named in order to be declined rather than approximated. Kept
    # to the two unambiguous spellings: 「落ちもの」 belongs to the catch
    # template below and must not be taken from it.
    ("落ち物パズル", "falling", ("テトリス", "tetris")),
    ("タワーディフェンス", "towerdefense", ("タワーディフェンス", "tower defense")),
    ("キャッチ", "catch", CATCH_WORDS),
    ("釣り", "fishing", FISHING_WORDS),
    # Last, matching choose_template: the bare 「ジャンプ」/「跳」 cues (C-1220)
    # name the platformer only when no genre above was named, so 「魚が跳ねる
    # 釣り」 stays fishing while 「猫がジャンプする」 becomes the platformer.
    ("プラットフォーマー", "platformer", PLATFORMER_WORDS),
)

#: Words that say "this is a game request" without naming a genre.
GENERIC_GAME_WORDS: tuple[str, ...] = (
    "ゲーム",
    "げーむ",
    "ミニゲーム",
    "game",
    "minigame",
    # Named works land on the game side even when no artifact class is
    # written down: 「ゼルダの伝説 不思議なぼうし作って」 names none. What
    # happens to the trademark is the generator's title guard, not the
    # detector's business.
    "ゼルダ",
    "ドラゴンボール",
)


def _game_words() -> tuple[str, ...]:
    """Every word that makes a request a game request, deduplicated.

    Built from the same table that routes, so a genre can never be
    routable and unrecognised at the same time - which is the whole defect
    C-1120 exists to close.
    """

    seen: list[str] = list(GENERIC_GAME_WORDS)
    for _label, _template, words in GENRES:
        for word in words:
            if word not in seen:
                seen.append(word)
    return tuple(seen)


#: What ``intent`` matches on. Derived, never hand-written again.
GAME_WORDS: tuple[str, ...] = _game_words()


def labels_for(templates) -> tuple[str, ...]:
    """The human names of the genres we can actually build, in table order."""

    out: list[str] = []
    for label, template, _words in GENRES:
        if template in templates and label not in out:
            out.append(label)
    return tuple(out)


__all__ = [
    "CATCH_WORDS",
    "FISHING_WORDS",
    "GAME_WORDS",
    "GENERIC_GAME_WORDS",
    "GENRES",
    "labels_for",
]
