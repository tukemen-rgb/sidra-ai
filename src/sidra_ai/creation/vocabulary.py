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

import re

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


#: C-1829: words that say *when* or *how eagerly* to make the thing, never
#: what to make. 「猫のゲームを今すぐ作って」 titled its page 「猫のゲームを今すぐ」:
#: every title builder cuts at the making verb, so a word sitting between the
#: artifact noun and that verb survives - and it also turns off the strip that
#: takes the kind word off the end, since that one is anchored to the end.
#: Measured across eight of these and six generators: 47 of 48 titles carried
#: the request's grammar.
#:
#: English already had the rule - ``_STRIP_EN_TAIL`` in ``games`` drops
#: please/thanks/for my kid (C-1528, C-1531) - and Japanese had only the
#: request markers ください and ほしい. Here rather than in one generator
#: because all six need the same list, which is what this module is for.
#:
#: Words that describe the ARTIFACT are deliberately absent: 「ざっくりした
#: アート」 and 「丁寧なレポート」 say what the thing should be like, and a title
#: that dropped them would be quoting less than the operator asked for. The
#: test for a row here is that it could be deleted from the request without
#: changing what gets made.
REQUEST_ADVERBS: tuple[str, ...] = (
    "今すぐ", "すぐに", "すぐ", "今から", "これから",
    "まとめて", "一気に", "一括で",
    "ちゃんと", "きちんと", "しっかり",
    "サクッと", "さくっと", "ささっと", "手早く",
    "とりあえず", "ひとまず", "ついでに",
    "急いで", "大至急", "早めに", "なるはやで", "至急",
    "できれば", "よかったら", "もしよければ",
)

_REQUEST_ADVERB_TAIL = re.compile(
    r"(?:" + "|".join(re.escape(word) for word in REQUEST_ADVERBS) + r")[\s　]*$"
)


#: C-1833: units that turn a number into a size or a count - how many slides,
#: how long the animation, how many models. A title is the name of the thing,
#: and 「5枚」 names no thing: 「5枚のスライドを作って」 titled its deck 「5枚」,
#: 「30フレームのGIFを作って」 its animation 「30フレーム」, and 「魚の3Dモデルを
#: 3つ作って」 its model 「魚3つ」. Measured across nine such requests: eight
#: titles carried the number.
#:
#: 年 is deliberately absent. 「2026年のゲーム」 is not a count, and whether a
#: year is a subject is a question nothing measured answers - so it stays where
#: C-1832 left it rather than being decided here by a word list.
#:
#: The generators keep their own patterns for *reading* a count (the note that
#: says what was really made needs the number); this one only takes it out of
#: the name.
SIZE_UNITS: tuple[str, ...] = (
    "枚", "ページ", "頁", "スライド", "字", "文字",
    "フレーム", "コマ", "秒", "分",
    "個", "つ", "体", "匹", "台", "点",
    "ステージ", "面", "レベル", "ラウンド",
    # C-1841: the English units, measured rather than guessed. After the
    # English frame came off, the only titles still carrying request grammar
    # were 「30 frame」, 「5」 and 「3 page」 - all of them this one cause, because
    # C-1833's table was Japanese-only. A digit has to come first, so 「page 3」
    # in a subject is untouched; only 「3 page」 is a size.
    "page", "pages", "slide", "slides", "frame", "frames",
    "second", "seconds", "minute", "minutes", "model", "models",
    "word", "words", "character", "characters",
)

_SIZE_PHRASE = re.compile(
    # The longest unit first, so 「slides」 is not left holding an 「s」 after
    # 「slide」 matches; Python's alternation takes the first that fits.
    r"\d{1,4}\s*(?:"
    + "|".join(re.escape(unit) for unit in sorted(SIZE_UNITS, key=len, reverse=True))
    + r")(?:(?:の|で|を)"
    # C-1841: the phrase ends either in the particle that attached it - 「5枚の
    # スライド」, 「スライドを5枚で」 - or at a real boundary. 「5枚組の写真集」 is a photo book
    # of five prints - a subject - and cutting 「5枚」 out of it quotes the
    # operator saying something they did not. The other loop's C-1822 avoided
    # this by anchoring its rule to the start of the request; this keeps the
    # freedom to match anywhere (「スライドを5枚で」 puts the size at the end) and
    # pays for it by requiring a boundary: a particle, a space, or the end.
    # Their test is what caught it - 「5枚組の写真集のレポート」 came back
    # 「組の写真集」 - which is the case for tests that pin somebody else's rule.
    r"|(?=$|[\s　]|[^\w\u3040-\u30ff\u4e00-\u9fff]))",
    re.IGNORECASE,
)


def drop_size_phrases(text: str) -> str:
    """The request without its 「5枚」「30フレーム」「3つ」, wherever they sit.

    A whole numeric phrase comes out - digits, unit, and the particle that
    attached it - never part of a word, so what is left is still a run of the
    operator's own characters (the C-1503 rule: a title has to be theirs by
    construction, not by luck).

    Anywhere rather than at one end, because the count moves: 「5枚のスライド」
    puts it in front and 「スライドを5枚で」 behind, and behind is also where it
    stops the end-anchored kind-word strip from firing at all.
    """

    out = _SIZE_PHRASE.sub("", text)
    return " ".join(out.split()).strip("　 ・")


#: C-1841: the frame an English request puts around what it wants. Japanese
#: ends with the making verb, so every generator's split takes it off; English
#: begins with it and only ``games`` had a rule (C-1516 onward). Measured
#: across fifteen English requests: twelve titles carried the sentence - a deck
#: called 「make a slide deck about the new product」, a report called 「write a
#: report about monetisation」.
#:
#: Three pieces, and the third is the interesting one. English says outright
#: which half is the subject: 「a model OF a fish」, 「a report ABOUT
#: monetisation」. The head noun comes first, which is the mirror of the
#: Japanese rule in C-1479, so the subject cannot be reached by trimming ends -
#: it has to be lifted out from behind the preposition.
_EN_HEAD = re.compile(
    r"^(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:(?:let\s*'?s\s+)?(?:make|create|build|generate|design|produce|draw|write|model)"
    r"|give\s+me|gimme|(?:i|we)\s*(?:'?d\s*|\s+would\s+)like|(?:i|we)\s+(?:want|need))"
    r"\s+(?:me\s+)?(?:a|an|the|some)?\s*",
    re.IGNORECASE,
)

_EN_SUBJECT = re.compile(
    r"^.*?\b(?:of|about|featuring|showing|starring)\s+(?:a|an|the|some)?\s*",
    re.IGNORECASE,
)

#: C-1842: the English half of ``REQUEST_ADVERBS``. English puts these at the
#: end - 「make a racing game right now」 - which is where the tail rule already
#: takes off please and thanks. Measured across five of them and six
#: generators before this: 30 titles out of 30 kept the adverb, while the
#: Japanese equivalents had all come off since C-1829.
#:
#: Same admission test as the Japanese table: a row belongs here only if
#: deleting it from the request changes nothing about what gets made.
ENGLISH_REQUEST_ADVERBS: tuple[str, ...] = (
    "right now", "right away", "as soon as possible", "asap",
    "when you can", "whenever you can", "at some point",
    "quickly", "fast", "soon", "now", "today", "tonight",
    "first", "already", "finally", "just",
)

_EN_TAIL = re.compile(
    r"\s*(?:please|thanks|thank you|"
    + "|".join(re.escape(word) for word in sorted(ENGLISH_REQUEST_ADVERBS, key=len, reverse=True))
    + r")\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def drop_english_frame(text: str) -> str:
    """The subject of an English request, with the sentence around it removed.

    Runs unconditionally, which is a measurement rather than a shortcut: every
    pattern needs an English word (make/create…, of/about…, please) that a
    Japanese sentence does not contain, and across ten Japanese requests this
    changed no title. C-1839 wrote a guard for exactly this and deleted it
    again for the same reason - a guard that decides nothing is dead code.

    The kind word is left to each generator's own trailing-kind rule, which
    already knows its own vocabulary: 「write a monetisation report」 leaves
    「monetisation report」 here and 「monetisation」 there.
    """

    stripped = text.strip()
    without_head = _EN_HEAD.sub("", stripped, count=1)
    lifted = _EN_SUBJECT.sub("", without_head, count=1)
    subject = " ".join((lifted or without_head).split())
    # C-1842: the tail comes off LAST, and never down to nothing.
    #
    # Both halves of that were measured. Taking it off first turned 「write a
    # report about today」 into 「report about」 - the tail rule had eaten the
    # word the 「about」 was pointing at, before the lift could read it. And
    # with the order fixed, that same request lifts to 「today」, where a rule
    # that removes it has stopped reading the request and started deleting it.
    # Repeatedly, because 「quickly right now」 stacks two.
    while True:
        shorter = _EN_TAIL.sub("", subject).strip()
        if not shorter or shorter == subject:
            return subject
        subject = shorter


def drop_request_adverbs(text: str) -> str:
    """The request without the words about when to make it, off the end.

    Applied until nothing more comes off - 「とりあえず今すぐ作って」 stacks two -
    and the particle that attached the adverb to the verb comes with it, so the
    kind-word strip that each generator runs next sees the end it expects.

    Only the tail: 「今すぐ帰りたい人のゲーム」 is a subject that happens to
    contain one of these words, and taking it from the middle would quote the
    operator saying something they did not (the C-1503 rule, one module over).
    """

    out = text.strip()
    while True:
        shorter = _REQUEST_ADVERB_TAIL.sub("", out).strip()
        if shorter == out:
            return out
        out = re.sub(r"[をにでと]+$", "", shorter).strip()


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
    "ENGLISH_REQUEST_ADVERBS",
    "CATCH_WORDS",
    "REQUEST_ADVERBS",
    "SIZE_UNITS",
    "drop_english_frame",
    "drop_request_adverbs",
    "drop_size_phrases",
    "FISHING_WORDS",
    "GAME_WORDS",
    "GENERIC_GAME_WORDS",
    "GENRES",
    "labels_for",
]
