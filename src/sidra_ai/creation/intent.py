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

Confidence is not a probability. It is a coarse three-step used by one
caller decision: only ``strong`` routes to a generator. ``weak`` means the
message looked like a creation request but the evidence was thin, and thin
evidence answers as a question - the conservative direction, since a missed
creation request costs an ordinary answer while a misread question costs a
confusing one.

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
            if best is None or index > best[0]:
                best = (index, kind, word)
    if best is None:
        return None
    return best[1], best[2]


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

    if not verb_hits:
        return CreationIntent(is_creation=False)

    if question_hits:
        # A making-verb inside a question is still a question. Reported as a
        # non-creation intent carrying its evidence, so the near miss is
        # visible to anyone auditing why a message was not routed.
        return CreationIntent(
            is_creation=False,
            confidence="vetoed",
            evidence=tuple(sorted(set(verb_hits + question_hits))),
        )

    artifact = _find_artifact(text)
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
