"""Revising an already-generated game instead of building a new one.

Every competitor's users ask for the same thing after the first artifact
appears: "make it harder", "change the colours", "rename it" - and the
market's chronic complaint (knowledge base §9) is tools that answer by
regenerating something new and different, side effects included. This
module is the other answer: the parameters a game was built from are kept
next to the artifact, a revision request edits those parameters, and the
page is rebuilt from the *same* request text - so everything the operator
did not mention stays byte-for-byte identical logic, and the old version
stays on disk.

No model decides anything here. The adjustment vocabulary is a table, so
「さっきのゲームをもっと難しくして」 behaves identically on the echo
backend and on the owner's PC - the property every routing decision in
this project holds, for the same measurement reason.

The metadata sidecar contains the operator's own (already gate-screened)
request text. It lives under the artifacts directory - the same local,
never-leaves-the-machine trust boundary as the artifact itself and the
retrieval index.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from collections.abc import Sequence
from pathlib import Path

from sidra_ai.creation.games import undepicted_subject
from sidra_ai.creation.games import (
    TEMPLATES,
    _DIFFICULTY,
    detect_genre,
    generate_game,
    save_game,
    validate_game_html,
)
from sidra_ai.creation.intent import (
    _EXPLANATION_QUESTION,
    _MAKE_VERBS,
    _QUESTION_MARKERS,
    fold_kana,
)
from sidra_ai.creation.router import CreationOutcome
from sidra_ai.creation.intent import CreationKind
from sidra_ai.creation.themes import DEFAULT_THEME, select_theme
from sidra_ai.creation.tuning import AXIS_LABELS

#: The one difficulty ladder the whole project uses, in climbing order.
#: Derived nowhere else: `_DIFFICULTY` in games.py keys per-template speeds
#: by exactly these three names.
_LADDER: tuple[str, ...] = ("easy", "normal", "hard")

#: Words that point back at something that already exists. One of these (or
#: the word ゲーム itself) has to appear: a bare 「難しくして」 with no
#: referent is not evidence the operator means a *game*, and the cost of a
#: false positive here is hijacking an ordinary question.
_BACK_REFERENCES: tuple[str, ...] = (
    "さっき",
    "先ほど",
    "昨日",
    "前の",
    "この前",
    "今の",
    "作った",
    "生成した",
    "ゲーム",
    "げーむ",
    # Demonstratives: right after making a game, 「その配色を紙にして」「これを
    # 速くして」「それを難しくして」 is the most natural way to point at it, and
    # without these the message fell to the question path and got the RAG
    # "no evidence, ask an admin to ingest a repository" wall (C-1257). Safe
    # here because the make-verb, question-marker and change-verb+adjustment
    # vetoes still gate every one: 「それは何ですか」 keeps its question marker,
    # 「これを作って」 keeps its make verb.
    "それ",
    "その",
    "これ",
    "この",
    # C-1513: 「忍者のやつを紙のテーマにして」 pointed at an existing page as
    # plainly as 「それ」 does and was declined, because やつ was in no table -
    # so 「さっきのやつ」 worked (さっき carried it) and 「忍者のやつ」 did not.
    # Safe for the same reason the demonstratives are: the make-verb,
    # question-marker and adjustment vetoes still gate every message, so
    # 「面白いやつを作って」 stays with the creation detector and 「あのやつは
    # 何ですか」 keeps its question marker.
    "やつ",
)

#: Adjustment vocabulary. Speed words map onto the difficulty ladder because
#: speed *is* what the ladder changes (`_DIFFICULTY` maps difficulty to
#: SPEED/BAND); a separate speed axis would let the two disagree.
#: C-1470: the adjectival forms above, plus the explicit idiom a player reaches
#: for after making a game - 「難易度を上げて/高くして」. Kept to the 「難易度を…」
#: forms so a bare 「上げて」 (「レベルを上げて」) does not read as a difficulty
#: change; the 上げて/下げて verbs are added to ``_CHANGE_VERBS`` so the gate lets
#: the instruction through.
_HARDER: tuple[str, ...] = (
    "難しく", "むずかしく", "ハードに", "速く", "はやく", "歯ごたえ",
    "難易度を上げ", "難易度をあげ", "難易度を高く",
)
_EASIER: tuple[str, ...] = (
    "簡単に", "かんたんに", "やさしく", "易しく", "遅く", "おそく", "ゆっくりに",
    "難易度を下げ", "難易度をさげ", "難易度を低く",
)

#: The panel's second axis, in words (C-1117). Deliberately *not* mapped
#: onto easier/harder: what the axis means differs per template - more
#: enemies in the adventure, a wider hit window in the fishing - and only
#: the panel's own label knows which. So the words move the number, and
#: the page says what the number is for.
_BAND_UP: tuple[str, ...] = ("広く", "ひろく", "増やして", "ふやして", "多く", "おおく")
_BAND_DOWN: tuple[str, ...] = ("狭く", "せまく", "減らして", "へらして", "少なく", "すくなく")

#: The accent, in words. Eight colours people actually ask for, and no
#: more: a colour vocabulary that guesses is a colour vocabulary that gets
#: it wrong silently. Themes still own the whole palette; this is the one
#: colour the templates paint their own things with.
_ACCENT_WORDS: dict[str, str] = {
    "赤": "#ff5a5a",
    "青": "#4aa8ff",
    "緑": "#5ad67d",
    "黄": "#ffd23f",
    "紫": "#b98cff",
    "橙": "#ff9f43",
    "桃": "#ff7ac0",
    "白": "#e8eef7",
}

#: The two switches. Each needs a direction, and the "off" words are
#: checked first so 「日替わりをやめて」 does not read as 「日替わりにして」.
_DAILY_WORDS: tuple[str, ...] = ("日替わり", "ひがわり", "今日の挑戦")
_BRIEF_WORDS: tuple[str, ...] = ("ブリーフィング", "説明画面", "作戦説明")
_OFF_WORDS: tuple[str, ...] = ("やめて", "止めて", "解除", "オフ", "off", "無し", "なしで", "飛ばして", "スキップ")

#: Undo, in words (C-1513). The product ends every revision with 「旧版の
#: ファイルもそのまま残っています」 - a promise about files the operator had
#: no sentence for. These are the sentences.
#:
#: Bare 「戻して」 is deliberately absent: it is already a ``_CHANGE_VERBS``
#: entry, and 「タイトルを『夜』に戻して」 is a rename, not an undo. Only the
#: explicit idioms are here, and even they yield to any other recognised
#: adjustment (see ``detect_revision_intent``), so 「タイトルを元に戻して」
#: keeps the meaning it has today.
_REVERT_WORDS: tuple[str, ...] = (
    "元に戻", "もとに戻", "元にもど", "もとにもど",
    "元通り", "もとどおり", "取り消し", "取消し", "取り消して", "取消して",
)

#: An undo that is the *whole* message (C-1513b). 「元に戻して」 typed on its
#: own is the sentence a person reaches for immediately after a change, and
#: it carried no ``_BACK_REFERENCES`` word, so it fell to the question path
#: and got the RAG no-evidence wall - the same hole C-1257 filled for the
#: demonstratives.
#:
#: Filling it by making the undo idiom a referent was measured first, as the
#: split required, and rejected: over 1,255 shipped strings (the four eval
#: question sets plus every Japanese literal in the suite) exactly one flips,
#: and it is this project's own test - but the sentences that flip are the
#: domain's own. 「設定を元に戻してください」, 「権限を元に戻してください」,
#: 「quarantine を元に戻して」 and 「索引を元通りにして」 are questions about
#: the product, and the reviser would have taken all four. The question-marker
#: veto does not stop them: ``_POLITE_REVISION`` exempts 「戻して＋ください」
#: as courtesy, which is right for a revision and wrong for these.
#:
#: What separates them is an object. 「設定を」「権限を」「索引を」 name what to
#: restore, and it is not the game; a bare undo names nothing, so there is
#: nothing else it could mean. So only the bare form counts - the idiom, any
#: politeness, and nothing else.
#: Matched with ``fullmatch``: the guard *is* that nothing else is in the
#: sentence, so start and end are both anchored on purpose rather than by
#: the accident of which regex method the caller reached for.
_BARE_UNDO = re.compile(
    r"(?:もう一度|もういちど|やっぱり|やはり)?\s*"
    r"(?:元に戻して|元にもどして|もとに戻して|もとにもどして"
    r"|元通りにして|もとどおりにして|取り消して|取消して|取り消しして)"
    r"(?:ください|下さい|くださる|ちょうだい|頂戴"
    r"|もらえますか|もらえませんか|もらえます|いただけますか|いただけませんか"
    r"|ほしい|欲しい|くれ|ね|よ|な)*"
    r"[\s。、！!？?]*"
)

#: 「タイトルを「◯◯」にして」/「名前を◯◯に変えて」. The quoted form wins#: 「タイトルを「◯◯」にして」/「名前を◯◯に変えて」. The quoted form wins
#: when both appear; the unquoted form stops at the particle.
_TITLE_QUOTED = re.compile(r"(?:タイトル|名前|題名)を?[「『\"']([^」』\"']{1,24})[」』\"']")
_TITLE_PLAIN = re.compile(r"(?:タイトル|名前|題名)を([^\s「『にへと]{1,24})に")

#: Change verbs. 作り直して is deliberately here and not in the creation
#: verbs: "remake it" names an existing thing, and routing it to a fresh
#: generation is exactly the competitor failure §9 records.
#: 「やめて」/「止めて」 are here for the switches C-1117 added: turning one
#: off is an instruction with no して in it, and without them
#: 「日替わりをやめて」 was vetoed as not-an-instruction. An adjustment still
#: has to be recognised afterwards, so widening this does not widen what
#: counts as a revision on its own.
_CHANGE_VERBS: tuple[str, ...] = (
    "して",
    "にして",
    "変えて",
    "かえて",
    "直して",
    "なおして",
    "やめて",
    "止めて",
    "戻して",
    "もどして",
    # C-1470: 「難易度を上げて／下げて」 is an instruction with no して in it,
    # exactly like the やめて／止めて above. Widening the gate does not widen
    # what counts as a revision on its own - an adjustment still has to be
    # recognised afterwards, so 「レベルを上げて」 passes here but finds none.
    "上げて",
    "上げる",
    "あげて",
    "下げて",
    "下げる",
    "さげて",
)

#: A polite request to change the game, phrased as a courteous imperative or a
#: request-question: a change verb te-form followed by a benefactive/honorific
#: auxiliary - 「難しくしてもらえますか」「配色を変えてください」. C-1463 is the twin of
#: C-1455 for revision: these end in 「ますか」/「ください」, which the shared
#: ``_QUESTION_MARKERS`` veto treats as a question, so a polite revision request
#: fell to the RAG no-evidence wall. A change stem plus a benefactive is a
#: request, not a question, and survives the veto unless it is also an
#: explanation question (``_EXPLANATION_QUESTION``). Folded to katakana to match
#: the normalised text the detector compares against.
_POLITE_REVISION = re.compile(fold_kana(
    r"(?:して|変えて|かえて|直して|なおして|やめて|止めて|戻して|もどして|"
    r"上げて|下げて|増やして|減らして|強くして|弱くして)"
    r"(?:(?:ください|下さい|くださ|ちょうだい)"
    r"|(?:もらえ|もらい|いただけ|いただき|頂け|頂き|くれ)[^。\n]{0,8}?か)"
))


@dataclass(frozen=True)
class RevisionIntent:
    """What the detector concluded about one message."""

    is_revision: bool
    #: Parameter deltas: "difficulty" -> "+1"/"-1", "theme" -> theme key,
    #: "title" -> new title. Empty means the message is not a revision.
    adjustments: dict[str, str] = field(default_factory=dict)
    evidence: tuple[str, ...] = field(default_factory=tuple)


def detect_revision_intent(message: str) -> RevisionIntent:
    """Decide whether a message asks to change an existing game.

    Three vetoes keep this conservative, in the same spirit as
    :func:`sidra_ai.creation.intent.detect_creation_intent`:

    * a creation verb (作って…) means the creation detector owns the
      message - a revision must never steal 「難しいゲームを作って」;
    * a question marker means it is a question about difficulty, not an
      instruction to change it;
    * no back-reference (or no recognisable adjustment) means we cannot
      know what to change, and guessing would edit an artifact nobody
      asked us to touch.
    """

    text = fold_kana(message.casefold())
    if not text.strip():
        return RevisionIntent(is_revision=False)
    if any(fold_kana(verb.casefold()) in text for verb in _MAKE_VERBS):
        return RevisionIntent(is_revision=False)
    # A polite request ("難しくしてもらえますか") ends in 「ますか」, which the shared
    # question-marker veto would treat as a question; it is courtesy, not an
    # asking verb, so it is exempt unless it is also an explanation question
    # (C-1463, the revision twin of C-1455).
    polite_request = bool(_POLITE_REVISION.search(text)) and not _EXPLANATION_QUESTION.search(text)
    if not polite_request and any(
        fold_kana(marker.casefold()) in text for marker in _QUESTION_MARKERS
    ):
        return RevisionIntent(is_revision=False)
    # C-1513b: a bare undo is its own referent. It points at the last change
    # rather than at a page, which is why no word in the table matched it -
    # and why widening that table was the wrong way to let it through.
    bare_undo = bool(_BARE_UNDO.fullmatch(message.strip()))
    if not bare_undo and not any(
        fold_kana(word.casefold()) in text for word in _BACK_REFERENCES
    ):
        return RevisionIntent(is_revision=False)
    if not any(fold_kana(verb) in text for verb in _CHANGE_VERBS):
        return RevisionIntent(is_revision=False)

    adjustments: dict[str, str] = {}
    evidence: list[str] = []

    if any(fold_kana(word) in text for word in _HARDER):
        adjustments["difficulty"] = "+1"
        evidence.append("difficulty+1")
    elif any(fold_kana(word) in text for word in _EASIER):
        adjustments["difficulty"] = "-1"
        evidence.append("difficulty-1")

    theme = select_theme(message)
    if theme is not DEFAULT_THEME:
        adjustments["theme"] = theme.key
        evidence.append(f"theme:{theme.key}")

    # The panel's own axes (C-1117). Difficulty is applied first and these
    # land on top, which is the order the words arrive in: 「難しくして、
    # でも敵は減らして」 means both, in that order.
    if any(fold_kana(word) in text for word in _BAND_UP):
        adjustments["band"] = "+1"
        evidence.append("band+1")
    elif any(fold_kana(word) in text for word in _BAND_DOWN):
        adjustments["band"] = "-1"
        evidence.append("band-1")

    for word, colour in _ACCENT_WORDS.items():
        if word in message:
            adjustments["accent"] = colour
            evidence.append(f"accent:{word}")
            break

    turned_off = any(fold_kana(word.casefold()) in text for word in _OFF_WORDS)
    if any(fold_kana(word) in text for word in _DAILY_WORDS):
        adjustments["daily"] = "off" if turned_off else "on"
        evidence.append(f"daily:{adjustments['daily']}")
    if any(fold_kana(word) in text for word in _BRIEF_WORDS):
        adjustments["brief"] = "off" if turned_off else "on"
        evidence.append(f"brief:{adjustments['brief']}")

    match = _TITLE_QUOTED.search(message) or _TITLE_PLAIN.search(message)
    if match:
        adjustments["title"] = match.group(1)
        evidence.append("title")

    # C-1513, and last on purpose: 「元に戻して」 means *undo the last change*,
    # so it only speaks when the message named no change of its own. That
    # keeps 「タイトルを元に戻して」 a rename to 「元」 - the behaviour it has
    # today - instead of quietly turning it into a whole-page undo, and it
    # is the conservative half of an ambiguity rather than a guess at it.
    if not adjustments and any(fold_kana(word) in text for word in _REVERT_WORDS):
        adjustments["revert"] = "1"
        evidence.append("revert")

    if not adjustments:
        # A back-reference and a change verb with nothing recognisable to
        # change. Reported as a non-revision so the question path can at
        # least answer; inventing a change would be worse than declining.
        return RevisionIntent(is_revision=False)

    return RevisionIntent(is_revision=True, adjustments=adjustments, evidence=tuple(evidence))


# ------------------------------------------------------------- metadata


def meta_path_for(artifact: Path) -> Path:
    return artifact.with_name(artifact.stem + ".meta.json")


def save_meta(
    artifact: Path,
    *,
    request: str,
    template: str,
    difficulty: str,
    theme: str,
    title: str,
    panel: dict | None = None,
) -> Path:
    """Record the parameters a page was built from, next to the page.

    Written on every generation, not only ones someone later revises: a
    sidecar that exists exactly when it is needed is a sidecar that is
    never there.
    """

    path = meta_path_for(artifact)
    path.write_text(
        json.dumps(
            {
                "request": request,
                "template": template,
                "difficulty": difficulty,
                "theme": theme,
                "title": title,
                # C-1117: what the panel opens with. Without it a second
                # sentence would rebuild from the ladder and quietly undo
                # what the first one turned.
                "panel": panel or {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _load_meta(path: Path) -> dict | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    if not all(isinstance(raw.get(k), str) for k in ("request", "template", "difficulty")):
        return None
    return raw


def _distinctive_name(meta: dict) -> str:
    """The part of a page's title that names *it* and not its genre.

    Reuses C-1125's rule, because it is the same question asked twice: what
    did the operator name, beyond the kind of thing they wanted? A title
    that is only its genre word ("パズル") comes back empty and is never
    matched by name - it would otherwise swallow every message mentioning
    puzzles, and a page titled 「ゲーム」 would swallow all of them.
    """

    title = str(meta.get("title") or "")
    template = str(meta.get("template") or "")
    if not title:
        return ""
    # A page the operator never named is not addressable by the name we
    # gave it. Without this the default 「タイミング釣り」 yielded the
    # "distinctive" name 「タイミング」, so 「タイミングを直して」 - or any
    # message that happened to contain it - would have picked a page
    # nobody had called anything.
    spec = TEMPLATES.get(template)
    if spec is not None and title == spec.default_title:
        return ""
    return undepicted_subject(str(meta.get("request") or title), template, title)


def _targeting_text(message: str) -> str:
    """The message with the *new* title taken out.

    Genre words inside a title being set are not a statement about which
    page is meant: 「ゲームのタイトルを「ゼルダの冒険」にして」 asks to rename
    the current page, and 冒険 there is part of the new name, not a request
    for the adventure game. Reading it as targeting made the refusal added
    for C-1511 fire on a legitimate rename - caught by
    ``test_title_revision_still_passes_the_trademark_guard`` rather than by
    the battery of phrasings written for the fix, which is why the battery
    is not the whole test.

    Only the genre step uses this. The name step is left reading the whole
    message, because that is what it did before and no defect has been
    measured there; narrowing it here would be an unmeasured change riding
    along with a measured one.
    """

    for pattern in (_TITLE_QUOTED, _TITLE_PLAIN):
        match = pattern.search(message)
        if match:
            return message[: match.start()] + message[match.end() :]
    return message


#: 「Xのゲーム」 - the message saying what the page it means is *about*.
#: C-1511b: the genre rule (C-1511) only refuses when X happens to be a
#: word the genre table knows, so 「さっきの将棋のゲームを難しくして」 and
#: 「猫のゲームを難しくして」 asserted an identity just as plainly and still
#: fell through to "latest". X is the non-hiragana run in front of の
#: because that is where the assertion lives: 「猫の」 as a whole is glued
#: together by the kana, and every bigram of it carries hiragana, which is
#: why ``subject_terms`` cannot see 猫 either (measured, C-1512).
#:
#: 「やつ」 joined the trigger in C-1513, in the same change that made it a
#: referent: 「忍者のやつを紙のテーマにして」 became a revision, and with it
#: 「将棋のやつを難しくして」 became a *silent* one - measured, and exactly the
#: failure C-1511b had just closed for 「〜のゲーム」. A word that can point at
#: a page can also name one that is not there.
#:
#: The trigger is deliberately not 「ほう」. That was
#: the phrasings the split warned would over-refuse (「色のほうを変えて」,
#: 「難易度のほうを上げて」) - and measuring them first, as the item asked,
#: showed the warning pointed at the wrong risk twice over: neither is a
#: revision at all (``detect_revision_intent`` returns False for both,
#: because 「色」 and 「難易度」 without a referent are not evidence a game is
#: meant), and requiring the word ゲーム excludes them anyway. What is left
#: is the sentence that says, in so many words, "the X game".
_NAMED_SUBJECT = re.compile(r"([゠-ヿ一-鿿A-Za-z0-9]{1,12})の(?:ゲーム|げーむ|やつ)")

#: Words that answer *which one*, not *what about*. 「前のゲームを簡単にして」
#: and 「今のゲームを紙の配色にしてもらえますか」 are shipped phrasings (both
#: pinned by tests) and both put a word in front of 「のゲーム」 - so without
#: this the fix would refuse two requests that land correctly today, which
#: is the over-narrowing the split told us to measure before shipping.
#:
#: 前 / 今 / 昨日 are not listed twice: they are already ``_BACK_REFERENCES``
#: entries and are matched from there. The rest are the same part of speech
#: and are listed because no table in this project holds them yet.
#:
#: A pointer word nobody thought of is not a silent wrong edit - it is a
#: refusal that says what does exist and asks which one. That asymmetry is
#: the whole reason this rule is allowed to be a vocabulary: the failure it
#: replaces edits the wrong file and reports success under its name.
_POINTER_WORDS: frozenset[str] = frozenset(
    {"今日", "本日", "最新", "最後", "最初", "直前", "前回", "今回", "以前", "昔",
     "別", "元", "先"}
)


def _asserted_subject(message: str) -> str:
    """What the message says the page is about, or "" if it says nothing.

    Reads the same text the genre step reads - a subject inside a *new*
    title is not a statement about which page is meant (「タイトルを
    「猫のゲーム」にして」 renames the current one), and that phrasing was
    measured to match here before ``_targeting_text`` was applied.
    """

    for word in _NAMED_SUBJECT.findall(_targeting_text(message)):
        if word in _POINTER_WORDS:
            continue
        if word in _BACK_REFERENCES or f"{word}の" in _BACK_REFERENCES:
            continue
        return word
    return ""


def existing_titles(data_dir: str | Path) -> list[str]:
    """The titles a revision could actually name, newest first.

    Used to tell an operator what *does* exist when the name they used
    matched nothing. Listing them is the difference between a refusal that
    helps ("あるのは「宇宙のシューティング」です") and one that only says no.
    """

    directory = Path(data_dir) / "artifacts"
    if not directory.is_dir():
        return []
    paths = sorted(
        directory.glob("game-*.meta.json"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    titles: list[str] = []
    for path in paths:
        meta = _load_meta(path)
        if meta is not None and meta["template"] in TEMPLATES:
            title = str(meta.get("title") or "").strip()
            if title and title not in titles:
                titles.append(title)
    return titles


def _previous_version(
    data_dir: str | Path, target: Path, meta: dict
) -> tuple[Path, dict] | None:
    """The version saved just before ``target`` in its own chain.

    A revision rebuilds from the *same* request text and writes a new file
    next to the old one, so the request is what ties a chain together - not
    the filename, which only carries a timestamp, and not the title, which
    a rename changes halfway along. Ordered by mtime like everything else
    here, so a same-second revision does not sort backwards.

    Two games made from the identical request text share a chain. That is
    the honest reading: they are the same page made twice, and undoing one
    to the other is what 「元に戻して」 asks for.
    """

    directory = Path(data_dir) / "artifacts"
    if not directory.is_dir():
        return None
    chain: list[tuple[Path, dict]] = []
    for path in sorted(
        directory.glob("game-*.meta.json"), key=lambda p: (p.stat().st_mtime, p.name)
    ):
        other = _load_meta(path)
        if other is None or other["template"] not in TEMPLATES:
            continue
        if other.get("request") != meta.get("request"):
            continue
        if other.get("template") != meta.get("template"):
            continue
        chain.append((path, other))
    for index, (path, _) in enumerate(chain):
        if path == target:
            return chain[index - 1] if index else None
    return None


#: A name this conversation claims to have made. Every generator and every
#: reviser puts the title in 「」 in its own sign-off, so the turn a client
#: replays carries the name whether or not the client understood it.
_QUOTED_TITLE = re.compile(r"[「『]([^」』\n]{1,40})[」』]")


def titles_in_history(
    history: Sequence[tuple[str, str]] | None,
) -> list[str]:
    """The artifacts this conversation's own turns name, newest last.

    ``chat`` is stateless by contract - "the client replays them, which
    means every turn is a claim rather than a record" - so this is read as
    a claim, and used only to *narrow*. A conversation cannot reach an
    artifact it does not name, and naming one it did not make buys nothing:
    typing that name in the message already did that (C-1126).
    """

    names: list[str] = []
    for turn in history or ():
        if len(turn) < 2:
            continue
        for name in _QUOTED_TITLE.findall(str(turn[1])):
            if name not in names:
                names.append(name)
    return names


def find_target_meta(
    data_dir: str | Path,
    message: str,
    history: Sequence[tuple[str, str]] | None = None,
) -> tuple[Path, dict] | None:
    """Pick the game a revision message refers to.

    Four rules, most specific first.

    **What it was called.** 「猫のほうを難しくして」 means the cat game, and
    nothing else can be meant - but 猫 is not a genre word, so before
    C-1126 the message fell through to "latest" and quietly adjusted
    whatever had been made most recently. The name is matched on its
    *distinctive* part, computed the same way C-1125 works out what a
    request actually named: a page titled 「パズル」 has nothing left once
    its genre word is removed, so it can never be picked this way and a
    message mentioning パズル goes to the genre rule below, where it
    belongs. Without that, one page called 「ゲーム」 would answer to every
    revision message ever typed.

    **What kind it is.** 「レースのほうを難しくして」 finds the racing game
    even when a puzzle was generated afterwards.

    **What it says it is about.** 「さっきの将棋のゲームを難しくして」 names a
    game as plainly as 「テトリスのゲーム」 does, but 将棋 is in no genre
    table, so before C-1511b it was indistinguishable from sentence glue
    and the edit landed on whatever was newest. A 「Xのゲーム」 whose X is
    not a pointer word refuses here for the same reason the genre rule
    refuses: the identity matched nothing.

    **Otherwise the latest**, which is what a bare 「難しくして」 means.

    Filenames sort by their timestamp suffix, so "latest" needs no extra
    bookkeeping.
    """

    directory = Path(data_dir) / "artifacts"
    if not directory.is_dir():
        return None
    candidates: list[tuple[Path, dict]] = []
    # Ordered by mtime, not filename: a same-second revision gets a serial
    # suffix that sorts *before* its original lexicographically, and "latest"
    # picking the pre-revision file would silently drop the revision chain.
    paths = sorted(
        directory.glob("game-*.meta.json"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    for path in paths:
        meta = _load_meta(path)
        if meta is not None and meta["template"] in TEMPLATES:
            candidates.append((path, meta))
    if not candidates:
        return None
    # C-1519: what the conversation itself made, before what the machine
    # happens to hold. 「それを難しくして」 means the thing this conversation
    # is about, and reading it as "whatever was written to this directory
    # last" edited another person's artifact and reported success under its
    # name - measured with two callers sharing one data directory, which is
    # what a served process is.
    #
    # Only ever a narrowing. A history that names nothing (an ordinary
    # question-and-answer conversation) changes nothing, and one that names
    # only artifacts that are not here refuses below rather than falling
    # through to somebody else's newest.
    remembered = titles_in_history(history)
    if remembered:
        own = [
            (path, meta)
            for path, meta in candidates
            if str(meta.get("title") or "") in remembered
        ]
        if not own:
            return None
        candidates = own
    # The name first: it can only mean one page, where a genre can mean
    # several and 「latest」 means whichever happened to be last.
    for path, meta in candidates:
        named = _distinctive_name(meta)
        if named and named in message:
            return path, meta
    requested = detect_genre(_targeting_text(message))
    if requested is not None:
        if requested.supported:
            for path, meta in candidates:
                if meta["template"] == requested.template:
                    return path, meta
        # The message named a kind, and nothing of that kind is here -
        # either because none was made, or because it is a kind this
        # project does not make at all (「テトリスのゲームを難しくして」
        # names 落ち物パズル, which has no template).
        #
        # Falling through to "latest" here is C-1511: the message asserted
        # an identity, the identity matched nothing, and the edit landed on
        # whatever happened to be newest - then reported back under *its*
        # name, so the operator reads 「宇宙のシューティングを修正しました」
        # in answer to a sentence about a game of shogi. A wrong name is
        # information, not noise: it usually means the operator has lost
        # track of what exists, and the one thing that cannot help them is
        # silently editing something else. The caller turns this into a
        # refusal that names what does exist.
        return None
    # C-1511b: the same assertion, made with a word the genre table does not
    # know. 「さっきの将棋のゲームを難しくして」 named a game; no page here is
    # about 将棋 (the name rule above had every title to match against and
    # matched none); so the honest answer is the one C-1511 already writes -
    # name what exists and ask which - not an edit to whatever was newest.
    if _asserted_subject(message):
        return None
    return candidates[0]


# ------------------------------------------------------------- applying


def _step_difficulty(current: str, delta: str) -> str:
    index = _LADDER.index(current) if current in _LADDER else 1
    index += 1 if delta == "+1" else -1
    return _LADDER[max(0, min(index, len(_LADDER) - 1))]


def _step_band(template: str, current, delta: str):
    """One notch along the band values the author actually shipped.

    The steps are the template's own three, not an arbitrary percentage: a
    request to widen something should land on a value the author chose,
    and cannot walk off the end of the span the panel allows.
    """

    steps = sorted({pair[1] for pair in _DIFFICULTY[template].values()})
    if not steps:
        return current
    if current is None:
        current = steps[len(steps) // 2]
    nearest = min(range(len(steps)), key=lambda i: abs(steps[i] - float(current)))
    nearest += 1 if delta == "+1" else -1
    return steps[max(0, min(nearest, len(steps) - 1))]


def _panel_after(template: str, panel: dict, adjustments: dict) -> dict:
    """The page's opening values, after the sentence.

    Difficulty is applied by the caller (it moves both axes through the
    ladder); these land on top of it, because that is the order the words
    were said in.
    """

    after = dict(panel)
    if "band" in adjustments:
        after["band"] = _step_band(template, panel.get("band"), adjustments["band"])
    if "accent" in adjustments:
        after["accent"] = adjustments["accent"]
    for flag in ("daily", "brief"):
        if flag in adjustments:
            after[flag] = adjustments[flag] == "on"
    return after


def build_game_reviser(data_dir: str | Path):
    """The revision handler the API calls; mirrors a generator's shape."""

    def revise(
        message: str,
        intent: RevisionIntent,
        history: Sequence[tuple[str, str]] | None = None,
    ) -> CreationOutcome:
        found = find_target_meta(data_dir, message, history)
        if found is None:
            # Honest and terminal: falling through to the question path
            # would answer a request we understood with something else.
            #
            # Two different refusals, because they are two different facts
            # (C-1511). "Nothing has been made" and "what you named is not
            # among the things that have been made" used to share a sentence
            # that only fitted the first, so an operator who mistyped a name
            # was told to go and create something they had already created.
            # Three different facts, three different sentences. C-1511 split
            # the first two - "nothing has been made" and "what you named is
            # not among the things that have been made" - because one
            # sentence only fitted the first. C-1519 adds the third, and it
            # is not a variant of either: the conversation's own artifacts
            # are gone from this machine. Offering the titles that *are*
            # here would be both wrong and a crossing - it reads another
            # caller's names out to this one.
            here = existing_titles(data_dir)
            remembered = titles_in_history(history)
            if remembered and not [name for name in remembered if name in here]:
                shown = "」「".join(remembered[:5])
                summary = (
                    f"この会話で作った「{shown}」が見つかりません。"
                    "もう一度作るか、今あるものを名前で指定してください。"
                )
            elif here:
                shown = "」「".join((remembered or here)[:5])
                summary = (
                    "その名前のゲームは見つかりません。"
                    f"あるのは「{shown}」です。"
                    "どれを修正するか、名前で指定してください。"
                )
            else:
                summary = (
                    "修正の依頼と受け取りましたが、修正できる生成済みゲームが"
                    "見つかりません。先に「◯◯ゲームを作って」で作成してください。"
                )
            return CreationOutcome(
                kind=CreationKind.GAME,
                handled=True,
                summary=summary,
                details={"revision": intent.adjustments, "target": ""},
            )
        target_path, meta = found

        # C-1513: 「元に戻して」. Every revision signs off with 「旧版のファイル
        # もそのまま残っています」 - and until now there was no sentence that
        # reached them, so the product promised a history nobody could walk.
        # Undo is not a delete: the older parameters are rebuilt into a new
        # file, so the version being left behind survives too and a second
        # 「元に戻して」 walks forward again rather than falling off the end.
        undone_from: dict | None = None
        if "revert" in intent.adjustments:
            previous = _previous_version(data_dir, target_path, meta)
            if previous is None:
                return CreationOutcome(
                    kind=CreationKind.GAME,
                    handled=True,
                    summary=(
                        f"「{meta.get('title') or 'ゲーム'}」はまだ一度も修正して"
                        "いないので、戻せる前の版がありません。"
                    ),
                    details={"revision": intent.adjustments, "target": str(target_path)},
                )
            undone_from, meta = meta, previous[1]

        difficulty = meta["difficulty"]
        if "difficulty" in intent.adjustments:
            difficulty = _step_difficulty(difficulty, intent.adjustments["difficulty"])
        theme = intent.adjustments.get("theme", meta.get("theme", ""))
        title = intent.adjustments.get("title", meta.get("title", ""))
        before_panel = meta.get("panel") if isinstance(meta.get("panel"), dict) else {}
        # A changed difficulty re-reads both axes off the ladder, so a band
        # the previous sentence set is not carried over it - the newer
        # instruction wins, and the two never disagree about this page.
        if "difficulty" in intent.adjustments:
            before_panel = {k: v for k, v in before_panel.items() if k != "band"}
        panel = _panel_after(meta["template"], before_panel, intent.adjustments)

        game = generate_game(
            meta["request"],
            template=meta["template"],
            difficulty=difficulty,
            theme_name=theme,
            title_override=title,
            panel=panel,
        )
        verdict = validate_game_html(game.html)
        path = save_game(game, data_dir)
        save_meta(
            path,
            request=meta["request"],
            template=game.template,
            difficulty=game.difficulty,
            theme=theme,
            title=game.title,
            panel=panel,
        )

        changed: list[str] = []
        if game.difficulty != meta["difficulty"]:
            changed.append(f"難易度 {meta['difficulty']}→{game.difficulty}")
        if theme and theme != meta.get("theme", ""):
            changed.append(f"配色 {theme}")
        if title and title != meta.get("title", ""):
            changed.append(f"タイトル「{game.title}」")
        labels = dict(zip(("speed", "band"), AXIS_LABELS.get(game.template, ("速さ", "広さ"))))
        if panel.get("band") != before_panel.get("band"):
            changed.append(f"{labels['band']} {panel['band']}")
        if panel.get("accent") != before_panel.get("accent") and "accent" in panel:
            changed.append("差し色")
        for flag, name in (("daily", "今日の挑戦"), ("brief", "ブリーフィング")):
            if flag in panel and panel.get(flag) != before_panel.get(flag, False):
                changed.append(f"{name} {'入' if panel[flag] else '切'}")
        if not changed:
            # Recognised adjustments that all landed on their current
            # values (already at max difficulty, same theme). Saying "done"
            # would claim a change that did not happen.
            changed.append("変更なし（すでにその設定です）")

        summary = (
            f"「{game.title}」を修正しました: " + "、".join(changed) + "。"
            "旧版のファイルもそのまま残っています。"
        )
        if undone_from is not None:
            # Said against the state the operator is *leaving*, because that
            # is the change they watched happen. Comparing against the
            # restored version would print 「変更なし」 - true of the rebuild
            # and useless to the person who asked.
            undone: list[str] = []
            if game.difficulty != undone_from.get("difficulty"):
                undone.append(f"難易度 {undone_from.get('difficulty')}→{game.difficulty}")
            if theme != undone_from.get("theme", ""):
                undone.append(f"配色 {theme or '既定'}")
            if game.title != undone_from.get("title", ""):
                undone.append(f"タイトル「{game.title}」")
            summary = (
                f"「{game.title}」を一つ前の版に戻しました"
                + (": " + "、".join(undone) + "。" if undone else "。")
                + "戻す前のファイルもそのまま残っています。"
            )
        if not verdict["playable"]:
            summary = (
                f"「{game.title}」を修正しましたが、遊べる状態ではありません: "
                + "、".join(str(f) for f in verdict["failures"])
            )
        return CreationOutcome(
            kind=CreationKind.GAME,
            handled=True,
            summary=summary,
            artifact_path=str(path),
            details={
                "revision": intent.adjustments,
                "template": game.template,
                "difficulty": game.difficulty,
                "playable": verdict["playable"],
            },
        )

    return revise


__all__ = [
    "RevisionIntent",
    "build_game_reviser",
    "detect_revision_intent",
    "find_target_meta",
    "meta_path_for",
    "save_meta",
]
