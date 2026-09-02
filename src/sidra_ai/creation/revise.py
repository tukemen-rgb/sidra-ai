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
from pathlib import Path

from sidra_ai.creation.games import (
    TEMPLATES,
    detect_genre,
    generate_game,
    save_game,
    validate_game_html,
)
from sidra_ai.creation.intent import _MAKE_VERBS, _QUESTION_MARKERS, fold_kana
from sidra_ai.creation.router import CreationOutcome
from sidra_ai.creation.intent import CreationKind
from sidra_ai.creation.themes import DEFAULT_THEME, select_theme

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
)

#: Adjustment vocabulary. Speed words map onto the difficulty ladder because
#: speed *is* what the ladder changes (`_DIFFICULTY` maps difficulty to
#: SPEED/BAND); a separate speed axis would let the two disagree.
_HARDER: tuple[str, ...] = ("難しく", "むずかしく", "ハードに", "速く", "はやく", "歯ごたえ")
_EASIER: tuple[str, ...] = ("簡単に", "かんたんに", "やさしく", "易しく", "遅く", "おそく", "ゆっくりに")

#: 「タイトルを「◯◯」にして」/「名前を◯◯に変えて」. The quoted form wins
#: when both appear; the unquoted form stops at the particle.
_TITLE_QUOTED = re.compile(r"(?:タイトル|名前|題名)を?[「『\"']([^」』\"']{1,24})[」』\"']")
_TITLE_PLAIN = re.compile(r"(?:タイトル|名前|題名)を([^\s「『にへと]{1,24})に")

#: Change verbs. 作り直して is deliberately here and not in the creation
#: verbs: "remake it" names an existing thing, and routing it to a fresh
#: generation is exactly the competitor failure §9 records.
_CHANGE_VERBS: tuple[str, ...] = ("して", "にして", "変えて", "かえて", "直して", "なおして")


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
    if any(fold_kana(marker.casefold()) in text for marker in _QUESTION_MARKERS):
        return RevisionIntent(is_revision=False)
    if not any(fold_kana(word.casefold()) in text for word in _BACK_REFERENCES):
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

    match = _TITLE_QUOTED.search(message) or _TITLE_PLAIN.search(message)
    if match:
        adjustments["title"] = match.group(1)
        evidence.append("title")

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


def find_target_meta(data_dir: str | Path, message: str) -> tuple[Path, dict] | None:
    """Pick the game a revision message refers to.

    Latest wins, unless the message names a genre we have a template for -
    「レースのほうを難しくして」 should find the racing game even when a
    puzzle was generated afterwards. Filenames sort by their timestamp
    suffix, so "latest" needs no extra bookkeeping.
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
    requested = detect_genre(message)
    if requested is not None and requested.supported:
        for path, meta in candidates:
            if meta["template"] == requested.template:
                return path, meta
    return candidates[0]


# ------------------------------------------------------------- applying


def _step_difficulty(current: str, delta: str) -> str:
    index = _LADDER.index(current) if current in _LADDER else 1
    index += 1 if delta == "+1" else -1
    return _LADDER[max(0, min(index, len(_LADDER) - 1))]


def build_game_reviser(data_dir: str | Path):
    """The revision handler the API calls; mirrors a generator's shape."""

    def revise(message: str, intent: RevisionIntent) -> CreationOutcome:
        found = find_target_meta(data_dir, message)
        if found is None:
            # Honest and terminal: falling through to the question path
            # would answer a request we understood with something else.
            return CreationOutcome(
                kind=CreationKind.GAME,
                handled=True,
                summary=(
                    "修正の依頼と受け取りましたが、修正できる生成済みゲームが"
                    "見つかりません。先に「◯◯ゲームを作って」で作成してください。"
                ),
                details={"revision": intent.adjustments, "target": ""},
            )
        _, meta = found

        difficulty = meta["difficulty"]
        if "difficulty" in intent.adjustments:
            difficulty = _step_difficulty(difficulty, intent.adjustments["difficulty"])
        theme = intent.adjustments.get("theme", meta.get("theme", ""))
        title = intent.adjustments.get("title", meta.get("title", ""))

        game = generate_game(
            meta["request"],
            template=meta["template"],
            difficulty=difficulty,
            theme_name=theme,
            title_override=title,
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
        )

        changed: list[str] = []
        if game.difficulty != meta["difficulty"]:
            changed.append(f"難易度 {meta['difficulty']}→{game.difficulty}")
        if theme and theme != meta.get("theme", ""):
            changed.append(f"配色 {theme}")
        if title and title != meta.get("title", ""):
            changed.append(f"タイトル「{game.title}」")
        if not changed:
            # Recognised adjustments that all landed on their current
            # values (already at max difficulty, same theme). Saying "done"
            # would claim a change that did not happen.
            changed.append("変更なし（すでにその設定です）")

        summary = (
            f"「{game.title}」を修正しました: " + "、".join(changed) + "。"
            "旧版のファイルもそのまま残っています。"
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
