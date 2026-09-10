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
    # Before ビーム対戦, and this order is the whole of C-1121. DUEL_WORDS
    # carries bare 「対戦」, so 「対戦格闘ゲームを作って」 matched the duel
    # first and got a beam fight with no caveat and a page titled 「対戦格闘」
    # - the wrong template, no apology, and a name claiming a genre this
    # product does not build. Naming the thing we must decline first costs
    # nothing that was measured: 「格闘」 appears in no other genre's words,
    # so only requests that say it move, and 「ビーム対戦」/「対戦ゲーム」
    # still reach the duel. The alternative the item offered - dropping
    # 「対戦」/「バトル」 from DUEL_WORDS - was measured too and is worse:
    # 「対戦ゲームを作って」 then names no genre at all.
    (
        "対戦格闘",
        "fighter",
        ("格闘", "fighting", "格ゲー"),
    ),
    ("ビーム対戦", "duel", DUEL_WORDS),
    (
        "シミュレーション",
        "simulation",
        ("シミュレーション", "simulation", "経営ゲーム"),
    ),
    ("ノベル", "novel", ("ノベルゲーム", "ノベル", "visual novel", "サウンドノベル")),
    # 「音楽ゲーム」 is the spelling that fell through (C-1505): 「音ゲー」 and
    # 「リズムゲーム」 were declined as a genre, but this one matched no
    # table and dropped to the *subject* path, so the reply was 「「音楽」の
    # 題材を描く型はまだ無い」 - a music game answered as though the operator
    # had asked for a game about music. The bare 「音楽」 stays out: 「音楽を
    # 作って」 is not a request for a rhythm game.
    ("リズム", "rhythm", ("リズムゲーム", "音ゲー", "音楽ゲーム", "rhythm")),
    # Falling blocks are not the match-clear board this product builds, so
    # this is named in order to be declined rather than approximated. Kept
    # to the two unambiguous spellings: 「落ちもの」 belongs to the catch
    # template below and must not be taken from it.
    ("落ち物パズル", "falling", ("テトリス", "tetris")),
    ("タワーディフェンス", "towerdefense", ("タワーディフェンス", "tower defense")),
    # Quiz, mahjong and card/board games are genres this product does not
    # build, but they were in no table, so detect_genre returned None and they
    # fell to the *subject* path - 「『クイズ』の題材を描く型はまだ無い」, as if
    # quiz were a thing to draw like 「猫」, and with no 「いま作れるのは …」 list
    # to point the user somewhere buildable (C-1240). Named here, like the
    # falling-block puzzle above, so they are declined as genres with the list.
    # Their template keys are absent from TEMPLATES, so they are unsupported by
    # construction.
    ("クイズ", "quiz", ("クイズ", "quiz")),
    ("麻雀", "mahjong", ("麻雀", "マージャン", "mahjong")),
    ("カードゲーム", "cardgame", ("カードゲーム", "トランプ", "card game")),
    ("ボードゲーム", "boardgame", ("ボードゲーム", "board game", "すごろく")),
    # Same gap, a few common genres along (C-1253): a bare 「ブロック崩しを作って」
    # or 「3目並べを作って」 carried no vocabulary word and no 「ゲーム」, so it came
    # back unknown and fell to the *question* path - the reader got an answer
    # about nginx, not a game. Named here so they route to the game path and are
    # declined with the buildable list. Non-trademark genres only; a registered
    # name (オセロ 等) is a business call and stays out (E 節).
    ("ブロック崩し", "breakout", ("ブロック崩し", "breakout", "block breaker", "アルカノイド")),
    ("三目並べ", "tictactoe", ("3目並べ", "三目並べ", "○×ゲーム", "まるばつ", "tic-tac-toe", "tictactoe")),
    ("クリッカー", "clicker", ("クリッカー", "clicker", "放置ゲーム", "idle game")),
    ("キャッチ", "catch", CATCH_WORDS),
    ("釣り", "fishing", FISHING_WORDS),
    # Last, matching choose_template: the bare 「ジャンプ」/「跳」 cues (C-1220)
    # name the platformer only when no genre above was named, so 「魚が跳ねる
    # 釣り」 stays fishing while 「猫がジャンプする」 becomes the platformer.
    ("プラットフォーマー", "platformer", PLATFORMER_WORDS),
)

#: The bare noun for "a game", in either language. Split out of
#: ``GENERIC_GAME_WORDS`` by C-1526 because two different questions were
#: reading one list: "is this a game request?" (yes for 「ゼルダ」 too) and
#: "is this word the thing being made rather than what it is about?" (no).
_GAME_NOUNS: tuple[str, ...] = ("ゲーム", "げーむ", "ミニゲーム", "game", "minigame")

#: Named works land on the game side even when no artifact class is
#: written down: 「ゼルダの伝説 不思議なぼうし作って」 names none. What
#: happens to the trademark is the generator's title guard, not the
#: detector's business. They are *subjects*, not artifact nouns.
_NAMED_WORKS: tuple[str, ...] = ("ゼルダ", "ドラゴンボール")

#: Words that say "this is a game request" without naming a genre.
GENERIC_GAME_WORDS: tuple[str, ...] = _GAME_NOUNS + _NAMED_WORKS

#: The noun that names the thing being made, rather than what it is about.
#:
#: C-1526: 「create a fishing game please」 was answered with 「ただし「game」
#: は絵として出てきません」 - the honesty note quoting the word for "game"
#: as the subject the page failed to draw. Japanese had no such list
#: either, and the same sentence came back for 「アプリを作って」.
#:
#: Kept apart from the genre words on purpose. A genre word is trimmed
#: because the page *delivered* that genre; an artifact noun is trimmed
#: because it never named a subject at all. Merging the two would strip
#: 「dragon」 out of 「a game about a dragon」 - a subject the page really
#: cannot draw - because DUEL_WORDS carries 「dragon ball」.
ARTIFACT_NOUNS: tuple[str, ...] = _GAME_NOUNS + (
    "アプリ",
    "アプリケーション",
    "app",
    "application",
    "ページ",
    "page",
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
