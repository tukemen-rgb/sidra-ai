"""Deciding whether a message asks for something to be made.

The rules are deterministic and written for Japanese first, because that is
what the operators type. Two things have to line up before a message counts
as a creation request:

1. an **imperative to make** ("作って", "生成して", "build me") - not merely
   the word "作る" appearing somewhere, and
2. an **artifact** the request is about (a game, a deck, a document).

Requiring both is what keeps "ゲームの作り方を教えて" (how do I make a game)
on the question side: it names an artifact but asks to be *told*, not to be
*given*. A question suffix like "教えて" / "どうやって" / "とは" vetoes the
imperative outright, because in Japanese the verb that carries the request
comes last, and the last verb here is the asking one.

Confidence is not a probability. It is a coarse four-step used by one
caller decision: only ``strong`` routes to a generator. ``weak`` means the
message looked like a creation request but the evidence was thin, and thin
evidence answers as a question - the conservative direction, since a missed
creation request costs an ordinary answer while a misread question costs a
confusing one.

``ambiguous`` is the fourth, and it is not a weaker ``weak``: it means the
message is *nothing but* the name of an artifact - 「racing game」, 「パズル」 -
so there is no evidence either way. Answering it as a question and building
it are both guesses, and the honest answer is to ask which (C-1670). It does
not route.

No model is required. A local model, when present, may enrich the parameters
of a job (title, difficulty), but it never decides the route: the route has
to behave identically on the echo backend the development container runs, or
the number measured here would not be the number an operator gets.
"""

from __future__ import annotations

from sidra_ai.creation.vocabulary import GAME_WORDS

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum


class CreationKind(str, Enum):
    """What the requester wants made.

    ``UNKNOWN`` is a real answer, not a failure: the message asks for
    something to be made but names nothing this project can build. It routes
    nowhere and is reported, so an operator can see the gap instead of
    receiving a silent question-answer.
    """

    GAME = "game"
    #: A whole production - scenario, structure, features, art, the page and
    #: a record - rather than only the playable page. Separate from ``GAME``
    #: because the two are different requests: routing "企画から作って" to the
    #: game generator would answer with a page and silently drop the four
    #: things the operator actually asked for.
    PROJECT = "project"
    DECK = "deck"
    DOCUMENT = "document"
    MODEL3D = "model3d"
    GIF = "gif"
    ART = "art"
    UNKNOWN = "unknown"


#: Verbs that ask for something to be produced. Kept as surface forms rather
#: than a stem plus inflection table: the false-positive cost of a loose stem
#: ("作" alone matches 作品, 作業, 制作会社) is exactly the failure this
#: detector exists to avoid.
_MAKE_VERBS: tuple[str, ...] = (
    "作って",
    "作ってく",
    "作成して",
    "制作して",
    "生成して",
    "つくって",
    "書いて",
    # 「描いて」 is 「書いて」's visual twin - the te-form imperative for drawing.
    # Without it 「絵を描いて」「イラストを描いて」 were not read as make requests and
    # fell to the no-evidence answer that sends a maker to repo ingestion, the
    # C-1261 mistake, while 「アートを描いて」 (a buildable ART ask) was missed too.
    # The bare imperative was the gap; the polite 「描いてください」 already routed
    # via the courtesy pattern. C-1606.
    "描いて",
    "組んで",
    "用意して",
    "出力して",
)

#: Same idea in English, matched on word boundaries.
_MAKE_VERBS_EN: tuple[str, ...] = (
    "make",
    "build",
    "create",
    "generate",
    "write",
    "draft",
)

#: Endings that turn the whole message back into a question even when a
#: making-verb appears earlier. Japanese puts the operative verb last, so
#: these win over anything before them.
_QUESTION_MARKERS: tuple[str, ...] = (
    "教えて",
    "どうやって",
    "どうすれば",
    "方法は",
    "作り方",
    "とは",
    "ですか",
    "ますか",
    "できますか",
    "は何",
    "なぜ",
    "why",
    "how do",
    "how can",
    "what is",
    "explain",
)

#: Artifact vocabulary. Order matters only for reporting the evidence; the
#: kind is decided by which group matched, and a tie is broken by the group
#: whose match appears later in the message, because Japanese noun phrases
#: put the head noun last ("ゲームのデッキ" is a deck).
_ARTIFACTS: dict[CreationKind, tuple[str, ...]] = {
    # Checked before GAME by the latest-match rule below only when its own
    # words appear; a request naming both ("ゲームを企画から作って") resolves
    # to PROJECT because `_find_artifact` breaks ties by position and the
    # project words come later in that sentence. The explicit test in
    # tests/test_creation_projects.py pins that, since the two kinds
    # overlapping is exactly where a silent regression would live.
    CreationKind.PROJECT: (
        "企画から",
        # 「一式」 is what makes these projects, not 「企画」 (C-1504). The
        # bare noun stays out on purpose: C-1263 drew the line at a single
        # 企画/計画 document, and 「ゲームの企画を作って」 is still one
        # document. Measured before the words went in - the same noun gave
        # three different answers: 「ゲームの企画一式を作って」 delivered a
        # fishing game titled 「ゲームの企画一式」, 「企画一式を作って」 was
        # declined as unknown, and 「ゲームを企画から作って」 ran the
        # project. Both spellings are listed because 「企画書一式」 does not
        # contain 「企画一式」 as a run of characters.
        "企画一式",
        "企画書一式",
        "一連",
        "一通り",
        "プロジェクト",
        "ゲーム制作",
        "制作一式",
        # Single-stage requests route here too, and `projects.requested_stages`
        # narrows to the one stage. Routing them to a "scenario generator"
        # instead would put the same file in two places depending on how the
        # operator phrased it.
        "脚本",
        "シナリオ",
        "構成",
        "画面遷移",
        "機能設定",
        "スプライト",
        "アセット",
        "制作記録",
    ),
    # C-1120: derived from the same table the router uses, so a genre can
    # never be buildable and unrecognised at once. It used to be a third
    # hand-written list, and 「レースを作って」 fell through it into the
    # retrieval boilerplate while choose_template knew exactly what to make.
    CreationKind.GAME: GAME_WORDS,
    CreationKind.DECK: (
        "デッキ",
        "スライド",
        "プレゼン",
        "資料",
        "ピッチ",
        "deck",
        "slides",
        "presentation",
        "pitch",
        # C-1250: the deck job already writes a .pptx (decks.save_pptx), so a
        # PowerPoint request is a deck request. Without these it came back
        # unknown and fell to the question path - 「…の pptx を作って」 even built
        # a fishing game. NFKC folds ＰＰＴＸ→pptx, casefold folds PowerPoint.
        "pptx",
        "パワポ",
        "powerpoint",
    ),
    CreationKind.DOCUMENT: (
        "文書",
        "ドキュメント",
        "記事",
        "レポート",
        "報告書",
        # C-1458: common Japanese document deliverables were unrecognised, so
        # 「議事録を作って」「マニュアルを作って」「提案書を作って」 fell to UNKNOWN and
        # were answered as a Q&A search instead of building the grounded report
        # the document generator produces (the same drop C-1455 fixed for polite
        # phrasing). These are all written documents the generator already
        # builds from evidence; a request that also names another kind still
        # resolves by the latest-match rule ("ゲームのマニュアル" is a document
        # about a game). Business-plan wording (企画/計画) is deliberately left
        # out so the C-1263 boundary with the game-production bundle is unmoved.
        "議事録",
        "マニュアル",
        "提案書",
        "仕様書",
        "要件定義書",
        "手順書",
        "説明書",
        "document",
        "report",
        "article",
    ),
    # "モデル" is the head noun of 「ゲームのモデル」 and wins the latest-match
    # tie-break there, which is the desired reading: an asset for the game.
    CreationKind.MODEL3D: (
        "3dモデル",
        "3d model",
        "3d",
        "モデル",
        "立体",
        "フィギュア",
        "obj",
    ),
    # Deliberately narrow: 「アニメーション」 alone stays with the project
    # pipeline (C-998 animates the game page); only wording that names a
    # *file format* or an image lands here. NFKC folds ＧＩＦ to gif, so the
    # ASCII entry covers the full-width spelling an IME produces.
    CreationKind.GIF: (
        "gif",
        "ジフ",
        "アニメ画像",
        "動く画像",
        "動くアイコン",
    ),
    # 「ゲームのアート」 reads as an asset request and the latest-match rule
    # already gives PROJECT's 素材 words their chance; what lands here is
    # wording that asks for artwork as the thing itself.
    CreationKind.ART: (
        "ジェネラティブアート",
        "生成アート",
        "アート",
        "壁紙",
        "generative art",
        "artwork",
        # C-1480: Japanese 「壁紙」「アート」 route here but the English words for
        # the same abstract art did not, so an English speaker was declined for
        # what SIDRA can make. Bare "art" stays out - it is a substring of chart,
        # part, smart and article - so the English cues are the whole phrases.
        "wallpaper",
        "abstract art",
        "digital art",
    ),
}

_EN_VERB_PATTERN = re.compile(
    r"\b(" + "|".join(_MAKE_VERBS_EN) + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CreationIntent:
    """What the detector concluded, and what it saw.

    ``evidence`` carries the matched substrings rather than the message. It
    exists so an operator can see *why* a message was routed, and it is safe
    to log: every entry is a literal from the tables above, never text the
    requester supplied.
    """

    is_creation: bool
    kind: CreationKind = CreationKind.UNKNOWN
    confidence: str = "none"
    evidence: tuple[str, ...] = field(default_factory=tuple)

    @property
    def routes(self) -> bool:
        """Whether this should reach a generator rather than the model.

        Only strong evidence routes. See the module docstring for why the
        uncertain case deliberately falls back to answering the question.
        """

        return self.is_creation and self.confidence == "strong"

    def to_dict(self) -> dict[str, object]:
        return {
            "is_creation": self.is_creation,
            "kind": self.kind.value,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


def fold_kana(text: str) -> str:
    """Map hiragana onto katakana so 「ぜるだ」 and 「ゼルダ」 compare equal.

    The vocabulary tables are written in katakana and kanji; an operator's
    IME writes whichever script came out. Without this fold the detector is
    a different program per script - measured: 「ぜるだみたいなげーむ
    つくって」 fell through to the fishing default while the katakana
    spelling routed correctly. Applied to *both* sides of every comparison,
    never to stored text.
    """

    return "".join(
        chr(ord(ch) + 0x60) if "぀" <= ch <= "ゖ" else ch for ch in text
    )


def _normalise(message: str) -> str:
    """Fold width, case and kana script so all spellings read the same.

    NFKC also maps full-width Latin to ASCII, which is what makes the English
    word-boundary pattern usable on text an operator typed in a Japanese IME.
    """

    return fold_kana(unicodedata.normalize("NFKC", message).casefold())


def _find_artifact(text: str) -> tuple[CreationKind, str] | None:
    """Return the artifact whose keyword sits latest in the message.

    Latest wins because the head noun of a Japanese noun phrase comes last:
    "ゲームの資料を作って" is a document about a game, not a game.
    """

    best: tuple[int, CreationKind, str] | None = None
    for kind, words in _ARTIFACTS.items():
        for word in words:
            index = text.rfind(fold_kana(word.casefold()))
            if index < 0:
                continue
            # Latest position wins (the head noun comes last). On a tie the
            # longer, more specific cue wins: GAME_WORDS carries "3d" and MODEL3D
            # carries "3d model", both starting at the same index in an English
            # 「make a 3D model」, so dict order alone built a game for a 3D-model
            # request (C-1479). Japanese avoided it because its 「モデル」 cue sits
            # after 「3d」 and already won by position; English has no such
            # trailing cue. A later game word (「3Dゲーム」) still wins by position.
            if best is None or index > best[0] or (index == best[0] and len(word) > len(best[2])):
                best = (index, kind, word)
    if best is None:
        return None
    return best[1], best[2]


#: A polite request to *make* the artifact, phrased as a courteous imperative
#: or a request-question: a making stem directly followed by a benefactive or
#: honorific auxiliary - 「作ってもらえますか」「作成いただけますか」「描いてください」.
#: Japanese business requests are overwhelmingly phrased this way; the bare
#: imperative 「作って」 is the exception, not the rule. The trailing 「ますか」 made
#: the blunt question veto fire on every one of these (C-1454), so a polite
#: 「資料を作成いただけますか」 was answered as a question instead of building the
#: deck. Recognising the request lets the veto spare it. An explanation
#: question ("作り方を教えてもらえますか") still loses: its stem is nominalised
#: (作り方, not a te-form making verb) so this does not match it, and even if a
#: request and an explanation are mixed, ``_EXPLANATION_QUESTION`` withdraws the
#: exemption. The gratitude form 「作ってくれてありがとう」 is excluded because the
#: benefactive branch requires a trailing 「か」 (a request), which it lacks.
#: Written in hiragana and folded to katakana to match the normalised text.
_POLITE_REQUEST = re.compile(fold_kana(
    r"(?:作って|つくって|書いて|描いて|組んで|作成して|作成|制作して|制作|"
    r"生成して|生成|用意して|用意|出力して|出力)"
    r"(?:(?:ください|下さい|くださ|ちょうだい)"
    r"|(?:もらえ|もらい|いただけ|いただき|頂け|頂き|くれ)[^。\n]{0,8}?か)"
))

#: Explanation-seeking markers that keep a message a question however politely a
#: making-verb is wrapped. The subset of the veto markers that name *asking*
#: rather than *courtesy*, so a polite request keeps its veto exemption only
#: when none of these is present.
_EXPLANATION_QUESTION = re.compile(fold_kana(
    r"教えて|どうやって|どうすれば|方法|作り方|とは|は何|なぜ"
))


#: Wanting the artifact is asking for it. Neither 「レースゲームが欲しい」 nor
#: "I want a shooting game" contains a making-verb, so both fell through to the
#: Q&A boilerplate: measured 2026-09-11, one request written 17 ways reached a
#: generator 12 times, and the five misses were all desire forms (C-1527). The
#: gap is in both languages, which is why this is not an English-only patch.
#:
#: Anchored to the artifact instead of matched anywhere in the message, because
#: wanting is not making unless the thing wanted *is* the artifact. 「ゲームの
#: 作り方が欲しい」 still loses (作り方 vetoes), and "I want to know about the
#: racing game repo" never matches: the desire has to sit directly in front of
#: the artifact word, through a determiner and at most two adjectives. That is
#: the same head-noun rule `_find_artifact` already uses, read from the other
#: side.
#:
#: 「用意して」 is already a making-verb, so 「資料を用意して」 builds a deck today;
#: 「資料が欲しい」 reaching the same place is the existing contract, not a new
#: one.
_DESIRE_AFTER_JA = re.compile(fold_kana(r"^[はがをも]{0,2}[\s、]*(?:欲しい|ほしい)"))

#: The courteous form of the same ask - the artifact and a please, with no verb
#: at all. 「ゲームをください」 is its Japanese twin, and `_POLITE_REQUEST` misses
#: it because that pattern requires a making stem in front of 「ください」.
_GIVE_AFTER_JA = re.compile(fold_kana(r"^[はがをも]{0,2}[\s、]*(?:ください|下さい)"))
#: C-1530: 「pls」/「plz」 are 「please」 - 「puzzle please」 routed and
#: 「puzzle pls」 fell through to the Q&A boilerplate on the abbreviation
#: alone.
_GIVE_AFTER_EN = re.compile(r"^\s*[,.!]?\s*(?:please|pls|plz)\b")

#: C-1530: the plainest give-request there is. 「パズルをください」 routed and
#: 「give me a racing game」 did not, which is the same sentence in the other
#: language; 「gimme」 is that sentence spoken.
_GIVE_BEFORE_EN = re.compile(
    r"\b(?:gimme|give\s+me)\s+"
    r"(?:a|an|the|some|another)?\s*(?:[a-z0-9'-]+\s+){0,2}$"
)

#: "I want", "we need", "I'd like", "I would like" - and deliberately not a
#: bare "I like", which is an opinion about a thing that already exists ("I
#: like this game"). Only the wanting verbs ask for one to appear.
_DESIRE_BEFORE_EN = re.compile(
    r"\b(?:i|we)\s*(?:'d\s*|\s+would\s+)like\s+|\b(?:i|we)\s+(?:want|need)\s+"
    r"(?!to\b)"
    r"(?:a|an|the|some|another)?\s*(?:[a-z0-9'-]+\s+){0,2}$"
)


def _asks_for_artifact(text: str, word: str) -> str | None:
    """Name the request form that asks for `word` itself, if any.

    Returns an evidence token - a literal from the tables above, never text the
    requester supplied - or ``None`` when the artifact is merely mentioned.
    Every occurrence is tried, not only the latest, because the artifact that
    decides the kind and the one the desire attaches to are the same word but
    need not be the same occurrence in a sentence that names it twice.
    """

    needle = fold_kana(word.casefold())
    start = text.find(needle)
    while start >= 0:
        before = text[:start]
        after = text[start + len(needle):]
        if _DESIRE_AFTER_JA.match(after):
            return "desire_request"
        if _GIVE_AFTER_JA.match(after) or _GIVE_AFTER_EN.match(after):
            return "give_request"
        if _DESIRE_BEFORE_EN.search(before):
            return "desire_request"
        if _GIVE_BEFORE_EN.search(before):
            return "give_request"
        start = text.find(needle, start + 1)
    return None


#: Punctuation, spacing and the particles a bare noun phrase may still carry.
#: Stripped only while deciding whether anything *else* was said, never from
#: text that is kept.
_BARE_LEFTOVERS = re.compile(
    fold_kana(r"[\s、。，．,.!?！？・「」\"'()（）]|の|が|を|は|も")
    # The English article is the same kind of leftover as the Japanese
    # particle - 「a racing game」 names a thing and asks nothing, exactly as
    # 「レースゲーム」 does. Whole words only: as substrings these would eat
    # the middle of 「a**the**letics」 and leave a bare noun looking like
    # something more was said.
    + r"|\b(?:a|an|the|some)\b"
    # C-1530: the vagueness wrapper a genre gets when it is named loosely.
    # 「パズルっぽいの」 and 「パズル」 are the same message with the same two
    # readings - the review measured the pair and found the first falling
    # through to the Q&A boilerplate while the second asked back, on four
    # characters of difference. These carry no subject of their own, so
    # subtracting them cannot turn a question into a bare name: 「ゲーム業界の
    # 市場規模」 still leaves 業界市場規模 and stays a question.
    + fold_kana(r"|っぽい|みたいな|みたい|ような|やつ")
)


#: C-1530: a request that names no thing at all. 「ひまだからなにか遊べる
#: もの」 and "surprise me" are asks, but there is no noun in them to route
#: on, so they reached retrieval and came back with the Q&A boilerplate -
#: told, in effect, that the corpus has nothing about wanting something.
#:
#: The indefinite pronoun alone will not do it. 「何かエラーが出てる」,
#: "something is broken" and "anything in the logs" are ordinary questions
#: about this repository and carry the same pronoun; a rule that read the
#: pronoun as a request answered all three with an offer to build something.
#: So the pronoun has to sit in a *wanting* context, and each language
#: shows that differently.
_UNNAMED_IDIOM = re.compile(r"\bsurprise\s+me\b")

#: Japanese: either the indefinite pronoun heading a bare 「もの」/「やつ」
#: (「なにか遊べるもの」), or that bare noun beside a wanting verb
#: (「…もの頼む」). 「READMEを見せてください」 has the verb but names a
#: subject, so the ください alone never triggers this.
_UNNAMED_PRONOUN_JA = re.compile(fold_kana(r"なにか|なんか|何か"))
_UNNAMED_BARE_NOUN = re.compile(fold_kana(r"もの|やつ"))
_UNNAMED_WANT_VERB = re.compile(fold_kana(r"頼む|ください|下さい|ほしい|欲しい"))

#: English: the pronoun plus something that makes it a want - what it is
#: for, or that it is for enjoyment - and no finite verb in between, which
#: is what separates "anything for my kid" from "anything that broke the
#: build".
_UNNAMED_WANT_EN = re.compile(
    r"\b(?:something|anything)\b"
    r"(?:(?!\b(?:is|are|was|were|has|have|had|does|did|went|looks|seems|"
    r"broke|failed|happened|changed)\b)[\s\w',-])*?"
    r"\b(?:fun|to\s+play|for\s+(?:my|our))\b"
)


def _wants_something_unnamed(text: str) -> bool:
    """Whether the message asks for a thing without saying which thing.

    Only consulted once an artifact has been looked for and not found, so
    「なにかゲームを作って」 never reaches here - it named one.
    """

    if _UNNAMED_IDIOM.search(text) or _UNNAMED_WANT_EN.search(text):
        return True
    if not _UNNAMED_BARE_NOUN.search(text):
        return False
    return bool(
        _UNNAMED_PRONOUN_JA.search(text) or _UNNAMED_WANT_VERB.search(text)
    )


def _only_names_the_artifact(text: str) -> bool:
    """Whether the message says nothing beyond which artifact it is about.

    「racing game」 is what an operator types to be handed one and what they
    type to go looking for one, and nothing in those two words tells the two
    apart (C-1527 measured it as the one phrasing of seventeen that no rule
    could honestly route). So the test is subtraction: take out every word
    from the artifact tables and see whether anything is left. 「ゲーム業界の
    市場規模は」 leaves 「業界市場規模」 and stays a question - which is the
    case this has to keep getting right, because turning a question into a
    clarifying prompt is the failure this module exists to avoid.

    Longest first, so removing 「ゲーム」 out of 「ミニゲーム」 cannot leave a
     「ミニ」 behind and make a bare request look like it said something more.
    """

    remaining = text
    words = sorted(
        (fold_kana(w.casefold()) for group in _ARTIFACTS.values() for w in group),
        key=len,
        reverse=True,
    )
    for word in words:
        if word and word in remaining:
            remaining = remaining.replace(word, " ")
    return not _BARE_LEFTOVERS.sub("", remaining).strip()


def detect_creation_intent(message: str) -> CreationIntent:
    """Classify one operator message.

    Returns a non-creation intent for anything that does not clearly ask for
    something to be produced. That default is the point: this runs in front
    of the ordinary question path, and it must not take questions away from
    it.
    """

    text = _normalise(message)
    if not text.strip():
        return CreationIntent(is_creation=False)

    question_hits = [
        marker for marker in _QUESTION_MARKERS if fold_kana(marker.casefold()) in text
    ]
    verb_hits = [verb for verb in _MAKE_VERBS if fold_kana(verb.casefold()) in text]
    verb_hits.extend(match.group(1).casefold() for match in _EN_VERB_PATTERN.finditer(text))

    # A polite request ("作ってもらえますか") is a making-verb too, and one the
    # bare _MAKE_VERBS list misses when the courtesy auxiliary swallows the te-
    # form or replaces して. It only counts as a request when it is not also an
    # explanation question.
    polite_request = bool(_POLITE_REQUEST.search(text)) and not _EXPLANATION_QUESTION.search(text)
    if polite_request:
        verb_hits.append("polite_request")

    # Asking for the artifact itself is a making-verb too, and the one the
    # surface-form tables cannot hold: it has no verb. Resolved here rather
    # than below because the artifact is what carries the request, so it has
    # to be in hand before deciding there is no request at all.
    artifact = _find_artifact(text)
    asked_for = _asks_for_artifact(text, artifact[1]) if artifact is not None else None
    if asked_for is not None:
        verb_hits.append(asked_for)

    if not verb_hits:
        if (
            artifact is None
            and not question_hits
            and not _EXPLANATION_QUESTION.search(text)
            and _wants_something_unnamed(text)
        ):
            # Asked for something and named nothing. Reported as a
            # non-creation intent with no kind - there is none - so the
            # caller can name what it can build rather than send the
            # operator to the index for a question they did not ask
            # (C-1530).
            return CreationIntent(
                is_creation=False,
                confidence="unnamed",
                evidence=("unnamed_want",),
            )
        if (
            artifact is not None
            and not question_hits
            and _only_names_the_artifact(text)
        ):
            # Named a thing and asked nothing. Reported as a non-creation
            # intent - it must not route - but carrying the kind, so the
            # caller can ask which rather than picking one of the two
            # answers and being wrong half the time (C-1670).
            return CreationIntent(
                is_creation=False,
                kind=artifact[0],
                confidence="ambiguous",
                evidence=(artifact[1].casefold(),),
            )
        return CreationIntent(is_creation=False)

    if question_hits and not polite_request:
        # A making-verb inside a question is still a question. Reported as a
        # non-creation intent carrying its evidence, so the near miss is
        # visible to anyone auditing why a message was not routed. A polite
        # request is exempt: its 「ますか」 is courtesy, not an asking verb.
        return CreationIntent(
            is_creation=False,
            confidence="vetoed",
            evidence=tuple(sorted(set(verb_hits + question_hits))),
        )

    if artifact is None:
        # "作って" with nothing to make. Recognised, deliberately unrouted:
        # answering it as a question at least tells the operator something,
        # while guessing an artifact would produce a thing nobody asked for.
        return CreationIntent(
            is_creation=True,
            kind=CreationKind.UNKNOWN,
            confidence="weak",
            evidence=tuple(sorted(set(verb_hits))),
        )

    kind, word = artifact
    return CreationIntent(
        is_creation=True,
        kind=kind,
        confidence="strong",
        evidence=tuple(sorted(set(verb_hits + [word.casefold()]))),
    )
