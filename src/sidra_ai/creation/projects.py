"""Everything one game needs, in one directory, produced in one pass.

"企画から作って" is a different request from "作って". A playable page answers
the second; the first asks for the things a person actually needs before and
around the page - what happens in it, how the screens connect, what the
controls and numbers are, the art, and a record of how it was made.

This module lays that out as a **project**: a directory under
``.sidra/artifacts/projects/<slug>/`` with one file per stage. Each stage is
a template with its headings and its default values, correct with no model
and no network. C-996 through C-999 fill those bodies in; this file decides
what exists, where it lives, and how a request maps onto it.

Two properties are load-bearing and easy to lose later:

* **A partial request produces a partial project, not a whole one.**
  "脚本だけ作って" writes ``scenario.md`` and nothing else. Scaffolding six
  files because six is the full set would bury the one thing that was asked
  for.
* **A stage that was written is distinguishable from one that was not.**
  ``ScaffoldedProject.stages`` lists what this run produced, so the summary
  an operator reads and the directory they open cannot disagree.
"""

from __future__ import annotations

from sidra_ai.creation.vocabulary import (
    drop_english_frame,
    drop_request_adverbs,
)

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from html import escape
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from sidra_ai.creation.evidence import Fact
from sidra_ai.creation import sprites as sprite_lib
from sidra_ai.creation import story
from sidra_ai.creation.games import (
    TEMPLATES,
    generate_game,
    genre_fallback_note,
    save_game,
    trademark_in,
)
from sidra_ai.creation.records import append_record
from sidra_ai.models.echo import _reply_in_japanese


class Stage(str, Enum):
    """One deliverable in a production.

    The names are the operator's words, not internal ones: an operator who
    asked for 脚本 should find ``scenario.md`` and recognise it.
    """

    SCENARIO = "scenario"
    STRUCTURE = "structure"
    FEATURES = "features"
    ASSETS = "assets"
    GAME = "game"
    LOG = "log"


#: Where each stage lands inside the project directory.
STAGE_FILES: dict[Stage, str] = {
    Stage.SCENARIO: "scenario.md",
    Stage.STRUCTURE: "structure.md",
    Stage.FEATURES: "features.md",
    Stage.ASSETS: "assets/",
    Stage.GAME: "game.html",
    Stage.LOG: "production-log.md",
}

#: The order a production is read in, and the order files are written.
STAGE_ORDER: tuple[Stage, ...] = (
    Stage.SCENARIO,
    Stage.STRUCTURE,
    Stage.FEATURES,
    Stage.ASSETS,
    Stage.GAME,
    Stage.LOG,
)

#: Words that name one stage. Matched literally, like the creation-intent
#: tables next door and for the same reason: a matcher loose enough to find
#: a stage in any sentence finds one in every sentence.
STAGE_WORDS: dict[Stage, tuple[str, ...]] = {
    Stage.SCENARIO: ("脚本", "シナリオ", "ストーリー", "scenario", "story", "script"),
    Stage.STRUCTURE: ("構成", "画面遷移", "フロー", "structure", "flow"),
    Stage.FEATURES: ("機能設定", "機能", "仕様", "features", "spec"),
    Stage.ASSETS: ("モデル", "素材", "スプライト", "アセット", "assets", "sprite"),
    Stage.GAME: ("本体", "プレイ", "game.html"),
    Stage.LOG: ("記録", "ログ", "production log", "log"),
}

#: Words that ask for the whole production rather than one piece of it.
WHOLE_PROJECT_WORDS: tuple[str, ...] = (
    "企画から",
    "一連",
    "一通り",
    "プロジェクト",
    "まとめて",
    "全部",
    # C-1462: 「制作一式」 is the project generator's own offered label
    # (_KIND_LABELS["project"]) and a PROJECT intent word, but it was not a
    # whole-project word, so 「新機能ローンチのゲーム制作一式を作って」 fell to the
    # stage matcher, where 「機能」 (inside 新機能, the subject) matched the FEATURES
    # cue and narrowed a full-set request to features.md alone - while the
    # summary still said 「制作一式を作りました」. It now forces the whole
    # production. 「制作一式」 rather than bare 「一式」 keeps 「アセット一式」 (a full
    # set of assets) narrowed to its own stage.
    "制作一式",
    "end to end",
    "from scratch",
)


@dataclass(frozen=True)
class ScaffoldedProject:
    """What one scaffold run produced.

    ``root`` is a directory on the operator's disk and nothing else. As
    everywhere in this package, generated files stay local; there is no route
    that sends one anywhere.
    """

    slug: str
    title: str
    root: Path
    stages: tuple[Stage, ...]
    whole_project: bool
    #: Repository-and-path labels the request retrieved, recorded in the log
    #: so a reader can see what the production was grounded in.
    evidence: tuple[str, ...] = field(default_factory=tuple)
    #: True when the requested title carried a trademark and was replaced.
    renamed: bool = False
    #: The game template the production's game.html was built on, or "" when the
    #: project has no game stage. Exposed so the summary can disclose a genre
    #: fall-back to the default template the same way the standalone game path
    #: does (C-1285) - the game_job says 「代わりに既定の…型で作りました」 and the
    #: project must not stay silent about the same substitution.
    game_template: str = ""

    @property
    def files(self) -> tuple[str, ...]:
        return tuple(STAGE_FILES[stage] for stage in self.stages)


def wants_whole_project(request: str) -> bool:
    text = unicodedata.normalize("NFKC", request).casefold()
    return any(word.casefold() in text for word in WHOLE_PROJECT_WORDS)


def requested_stages(request: str) -> tuple[Stage, ...]:
    """Which stages this request asks for, in production order.

    A request naming no stage and no whole-project word still gets the whole
    project: "ゲームを企画から作って" and "ゲームを作って" differ, but so do
    "脚本を作って" and "ゲームを作って" - the middle case is the only one
    where narrowing is what the operator asked for.
    """

    if wants_whole_project(request):
        return STAGE_ORDER

    text = unicodedata.normalize("NFKC", request).casefold()
    named = tuple(
        stage
        for stage in STAGE_ORDER
        if any(word.casefold() in text for word in STAGE_WORDS[stage])
    )
    return named or STAGE_ORDER


def slugify(title: str, *, stamp: str) -> str:
    """A directory name that is safe on every filesystem and unique per title.

    The stamp is always present, so a directory name says when it was made.
    It is not enough on its own: a Japanese title carries no ASCII to slug,
    so two different requests in the same second both reduced to
    ``project-<stamp>`` and the second one wrote into the first one's
    directory. Measured, not imagined - "釣りゲームを企画から作って" and
    "釣りゲームの脚本だけ作って" collided on the first run of this module.

    So the title is also hashed. Deterministic rather than random: the same
    request at the same second must produce the same path, or a caller could
    not find what it just wrote.
    """

    folded = unicodedata.normalize("NFKC", title).casefold()
    ascii_part = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:32]
    digest = hashlib.sha256(folded.encode("utf-8")).hexdigest()[:6]
    prefix = ascii_part or "project"
    return f"{prefix}-{digest}-{stamp}"


#: The kind word a request tacks onto the subject: 「制作一式」「プロジェクト一式」
#: 「プロジェクト」「一式」, with an optional preceding の. Stripped from the title
#: so the summary 「『X』の制作一式を作りました」 does not echo it twice - the same
#: title cleanup documents (C-1246), decks (C-1249) and art/GIF (C-1265) got.
_TITLE_KIND_SUFFIX = re.compile(r"(?:の)?(?:制作一式|プロジェクト一式|プロジェクト|一式)$")


def _title_from(request: str) -> str:
    """The operator's own words, cut at the making-verb."""

    stripped = re.split(r"を?(?:作って|作成して|生成して|つくって)", request)[0]
    # C-1938: the English frame, exactly as art / decks / documents / gifs /
    # models3d all take it off at this same point. This generator was the one
    # that never did, so 「make a game project about an owl」 became the title
    # verbatim - and the title is the directory name and the heading of six
    # generated files, so the operator's own sentence became a folder called
    # `make-a-game-project-about-an-owl-...`. Same family as C-1913 and
    # C-1916, on the surface those two did not reach.
    stripped = drop_english_frame(stripped)
    # C-1829: the words about when to make it come off first, or 「猫のゲームを
    # 企画から今すぐ作って」 names the production 「猫のゲームを 今すぐ」.
    stripped = drop_request_adverbs(stripped)
    stripped = re.sub(r"(企画から|一連で|一通り|まとめて|だけ)", " ", stripped)
    stripped = " ".join(stripped.split())
    stripped = drop_request_adverbs(stripped)
    # Removing "企画から" from "釣りゲームを企画から作って" leaves the particle
    # that used to attach to it, and "釣りゲームを" is not a title. Trailing
    # particles are dropped here rather than in the split, because which one
    # is left over depends on which phrase was removed.
    stripped = re.sub(r"[をのはがにで]+$", "", stripped).strip()
    # Drop the kind word so the summary does not read 「制作一式」の制作一式を.
    # A request that is only the kind word (「制作一式を作って」) strips to nothing
    # and falls to the default below - keeping 「制作一式」 would echo it anyway.
    stripped = _TITLE_KIND_SUFFIX.sub("", stripped)
    # C-1829: .strip() BEFORE the particle removal, not after. Removing 「一式」
    # leaves 「レースゲームを 」 with the space the phrase removal above put
    # there, the anchored pattern then matches nothing, and the dangling
    # particle becomes the name of six files - measured on 5 of 14 requests.
    stripped = re.sub(r"[をのはがにで]+$", "", stripped.strip()).strip()
    return stripped[:60] or "無題のゲーム"


def _front_matter(
    title: str,
    stage: str,
    evidence: tuple[str, ...],
    *,
    in_japanese: bool = True,
) -> str:
    # Escape the title (from the request) and every source label (an indexed
    # Issue/PR path, EXTERNAL trust) so HTML in either is displayed, not executed,
    # in a Markdown renderer that permits inline HTML (C-1486, the projects twin
    # of the document C-1483). The stored .title stays raw for the chat summary.
    #
    # C-1940: ``in_japanese`` defaults to Japanese because the three design
    # documents stay Japanese until the template registry has English for the
    # rows that fill them (C-1939) - only the production log passes False.
    none_line = (
        "- （このステージに使える索引の根拠は見つかりませんでした）"
        if in_japanese
        else "- (no indexed source was found for this stage)"
    )
    sources = (
        "\n".join(f"- {escape(line, quote=False)}" for line in evidence)
        if evidence
        else none_line
    )
    if in_japanese:
        provenance = "> SIDRA AI が生成した骨格です。中身は各ステージの担当が埋めます。"
        sources_heading = "## 根拠にした索引"
    else:
        provenance = (
            "> A skeleton generated by SIDRA AI. The owner of each stage fills "
            "in the contents."
        )
        sources_heading = "## Sources indexed"
    return (
        f"# {escape(title, quote=False)} — {stage}\n\n{provenance}\n\n"
        f"{sources_heading}\n\n{sources}\n"
    )


def _scenario_skeleton(title: str, evidence: tuple[str, ...]) -> str:
    return _front_matter(title, "脚本", evidence) + """
## あらすじ

〔未記入〕

## 登場するもの

| 名前 | 役割 | 見た目のメモ |
|---|---|---|
| 〔未記入〕 | 〔未記入〕 | 〔未記入〕 |

## 場面

1. 〔未記入〕
"""


def _structure_skeleton(title: str, evidence: tuple[str, ...]) -> str:
    return _front_matter(title, "構成", evidence) + """
## 画面フロー

タイトル → プレイ → リザルト → タイトル

## 各画面

| 画面 | 出るもの | 次へ進む条件 |
|---|---|---|
| タイトル | 〔未記入〕 | 〔未記入〕 |
| プレイ | 〔未記入〕 | 〔未記入〕 |
| リザルト | 〔未記入〕 | 〔未記入〕 |
"""


def _features_skeleton(title: str, evidence: tuple[str, ...]) -> str:
    return _front_matter(title, "機能設定", evidence) + """
## 操作

| 入力 | 動作 |
|---|---|
| 〔未記入〕 | 〔未記入〕 |

## スコア

〔未記入〕

## 難易度パラメータ

| 名前 | easy | normal | hard |
|---|---|---|---|
| 〔未記入〕 | 〔未記入〕 | 〔未記入〕 | 〔未記入〕 |
"""


def _log_skeleton(
    title: str,
    stages: tuple[Stage, ...],
    evidence: tuple[str, ...],
    fallback: str = "",
    *,
    in_japanese: bool = True,
) -> str:
    """The production log, in the language the request was written in.

    C-1940. The other three documents of a production set are still Japanese
    for an English request, and this one is not, because it is the only one
    of the four whose text is entirely this module's own: the design
    documents are filled with ``TEMPLATES[...].how_to_play``, the control
    labels and the parameter names, which the registry holds in Japanese
    alone. Translating the frame around Japanese rows would ship the
    half-translated document C-1929's sabotage D4 exists to punish. So the
    unit is one **file**, finished, rather than four frames.
    """

    made = "\n".join(f"- {STAGE_FILES[stage]}" for stage in stages)
    # C-1605: the chat summary admits when game.html fell back to the default
    # template (C-1285), but the project is a directory that is saved and
    # forwarded, so the record itself has to say it too - the same reason the
    # report discloses its set-aside evidence (C-1281) and the 3D preview its
    # default shape (C-1283). Only when there was a fallback; a genuine game
    # request leaves this out rather than drawing a false caveat.
    fallback_heading = (
        "## 既定テンプレートへのフォールバック"
        if in_japanese
        else "## Fell back to the default template"
    )
    fallback_section = (
        # .strip() because the English sentence carries a leading space: it is
        # written to be appended after a chat sentence, and here it is a
        # section body of its own. Byte-identical for the Japanese one.
        f"\n{fallback_heading}\n\n{escape(fallback.strip(), quote=False)}\n"
        if fallback
        else ""
    )
    if in_japanese:
        body = f"""
## この回で作ったもの

{made}

## 追記の決まり

生成のたびに「いつ・何を・どの根拠（引用元 path）・どのパラメータで」を 1 行足す。
**索引した文書の中身はここに書かない**（path と日時とパラメータだけ）。
"""
    else:
        body = f"""
## Made in this run

{made}

## How to append

Add one line every time this is generated: when, what, from which source
(the quoted path) and with which parameters.
**Never write the contents of an indexed document here** - paths, times and
parameters only.
"""
    stage_name = "制作記録" if in_japanese else "Production log"
    return (
        _front_matter(title, stage_name, evidence, in_japanese=in_japanese)
        + fallback_section
        + body
    )


#: The three written stages. Each takes ``(title, evidence, plan)`` and fills
#: in the production's real controls and difficulty numbers - see
#: :mod:`sidra_ai.creation.story` for why they are derived rather than
#: invented. The ``_*_skeleton`` functions above are kept as the shape these
#: replaced; nothing calls them any more.
SKELETONS = {
    Stage.SCENARIO: story.scenario,
    Stage.STRUCTURE: story.structure,
    Stage.FEATURES: story.features,
}


def scaffold_project(
    request: str,
    data_dir: str | Path,
    *,
    facts: list[Fact] | None = None,
    now: datetime | None = None,
) -> ScaffoldedProject:
    """Create the project directory and every stage the request asked for.

    Deterministic apart from the timestamp, which the caller may pin. No
    model is consulted and nothing is fetched: a stage that cannot be written
    without a model would make this whole path untestable on the container
    that has none.
    """

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    title = _title_from(request)
    renamed = bool(trademark_in(title))
    if renamed:
        # Same deal as the standalone page (C-1011): the genre is buildable,
        # the name is someone's. The production takes its game's own default
        # title, and the fact is recorded on the project so the summary can
        # say it instead of renaming silently.
        title = TEMPLATES[story.plan_for(request).template].default_title
    slug = slugify(title, stamp=stamp)
    stages = requested_stages(request)
    evidence = tuple(dict.fromkeys(fact.source for fact in (facts or []) if fact.source))

    # Read once, before any stage is written: every document has to describe
    # the same production, and re-deriving per stage is how two files end up
    # disagreeing about the same game.
    plan = story.plan_for(request)
    # C-1790: the substitution admission (or "") that every document about this
    # production has to carry when the request named a genre we cannot build.
    # Computed once from the shared source (genre_fallback_note) so the design
    # docs, the production log and the chat summary all say the same thing, and
    # only when a game was actually built - the sentence speaks of game.html.
    fallback = genre_fallback_note(
        request, plan.template if Stage.GAME in stages else "", title
    )
    # C-1940: the production log follows the language of the request, by the
    # same rule every reply surface follows (``_reply_in_japanese``, the
    # product's own SYSTEM_PROMPT rule 6). The three design documents do not
    # yet, and that is deliberate: their rows come from the template registry,
    # which holds 操作 labels, パラメータ names and how_to_play in Japanese
    # alone, so an English frame around them is the half-translated document
    # this loop has refused three times. One finished file beats four
    # half-finished ones.
    in_japanese = _reply_in_japanese(request)
    # The same admission, in the log's language. Computed separately rather
    # than reused: `fallback` goes into the Japanese design documents, and a
    # document does not change language in the middle of itself.
    # C-1942: the same sentence is now needed by every document that follows
    # the request's language, not only the log, so the name says what it is.
    translated_fallback = (
        fallback
        if in_japanese
        else genre_fallback_note(
            request,
            plan.template if Stage.GAME in stages else "",
            title,
            in_japanese=False,
        )
    )
    # Filled by the assets stage and read by the game stage. Empty when the
    # request asked for a game without assets, which is a supported shape:
    # the page then draws what it always drew.
    asset_paths: dict[str, str] = {}

    root = Path(data_dir) / "artifacts" / "projects" / slug
    root.mkdir(parents=True, exist_ok=True)

    for stage in stages:
        if stage in SKELETONS:
            if stage is Stage.STRUCTURE:
                # C-1942: the one design document whose text this repo owns
                # end to end - its rows are story.py's own prose plus the
                # control *keys*. `scenario` and `features` read the template
                # registry's Japanese (how_to_play, the control meanings, the
                # parameter labels) and stay Japanese until it has English,
                # because a frame in one language over rows in another is the
                # half-translated document this loop has refused five times.
                #
                # Named here rather than kept in a table of "stages that can
                # do English": a table would hold a row per stage still
                # waiting, and a row is exactly what nobody deletes.
                written = story.structure(
                    title,
                    evidence,
                    plan,
                    translated_fallback,
                    in_japanese=in_japanese,
                )
            else:
                written = SKELETONS[stage](title, evidence, plan, fallback)
            (root / STAGE_FILES[stage]).write_text(written, encoding="utf-8")
        elif stage is Stage.ASSETS:
            # Seeded from the request, so regenerating a project gives the
            # same art its own documents already describe.
            sprite_lib.save_sprites(
                sprite_lib.generate_sprites(
                    plan.template, seed=sprite_lib.seed_for(request)
                ),
                root / "assets",
            )
            # Resolved from the directory rather than from what was just
            # written, so a picture the operator already dropped in (or, once
            # the owner installs a local image model, one it produced) wins
            # over the procedural SVG. That is the whole receptacle: filling
            # a slot is putting a file in assets/, not editing anything.
            asset_paths = sprite_lib.resolve_slots(plan.template, root / "assets")
        elif stage is Stage.GAME:
            # The playable page already exists as a generator, so the project
            # gets a real one rather than an empty file. Saved under the
            # project rather than beside it: the point of a project is that
            # one directory holds the whole production.
            # The page references the sprites written above by relative path.
            # Relative, not embedded: a project is a directory, and an
            # operator who repaints target.svg should see the change without
            # regenerating the game. It falls back to the plain shapes when a
            # file is missing, so an emptied assets/ costs the look, not play.
            game = generate_game(
                request, evidence=list(evidence) or None, sprites=asset_paths,
                # C-1621: carry the project's canonical title, not one the game
                # re-derives from the raw request - that kept 「制作一式」 and made
                # game.html disagree with every .md, the exact per-stage
                # re-derivation the note above warns against.
                title_override=title,
            )
            (root / "game.html").write_text(game.html, encoding="utf-8")
        elif stage is Stage.LOG:
            (root / STAGE_FILES[stage]).write_text(
                _log_skeleton(
                    title, stages, evidence, translated_fallback,
                    in_japanese=in_japanese,
                ),
                encoding="utf-8",
            )

    if Stage.LOG in stages:
        # The record of this run, appended by machinery rather than left as a
        # rule for someone to follow. Only when the LOG stage exists: a
        # partial project stays partial, and the record rule (C-999) never
        # overrides the partial-request rule the tests pin. Paths, time and
        # parameters only - the evidence entries are source labels, never the
        # text they pointed at.
        append_record(
            root,
            made=[STAGE_FILES[stage] for stage in stages],
            evidence=list(evidence),
            parameters={
                "template": plan.template,
                "difficulty": plan.difficulty,
                "speed": plan.speed,
                "band": plan.band,
            },
            now=now,
            in_japanese=in_japanese,
        )

    return ScaffoldedProject(
        slug=slug,
        title=title,
        root=root,
        stages=stages,
        whole_project=wants_whole_project(request),
        evidence=evidence,
        renamed=renamed,
        game_template=plan.template if Stage.GAME in stages else "",
    )


#: A stage counts as written when it says something specific about *this*
#: production. Length alone would pass a page of generic prose, and a heading
#: check would pass the placeholder version this replaced, so the test is a
#: fact only the real parameters could supply.
def _stage_is_substantive(text: str, plan: "story.ProductionPlan") -> bool:
    facts = [str(plan.speed), str(plan.band)]
    facts += [key for key, _ in plan.controls]
    facts += [label for label, _ in plan.parameters]
    return any(fact and fact in text for fact in facts)


def count_substantive_stages(project: ScaffoldedProject, plan: "story.ProductionPlan") -> int:
    """How many written stages carry the production's own numbers.

    Reads the disk rather than the return value: a scaffolder that reported
    three stages and wrote one is exactly the failure the project validator
    exists for, and this number would inherit the same blind spot.
    """

    written = 0
    for stage in (Stage.SCENARIO, Stage.STRUCTURE, Stage.FEATURES):
        if stage not in project.stages:
            continue
        target = project.root / STAGE_FILES[stage]
        if not target.is_file():
            continue
        if _stage_is_substantive(target.read_text(encoding="utf-8"), plan):
            written += 1
    return written


def validate_project(project: ScaffoldedProject) -> dict:
    """Report every stage the run claimed but did not actually write.

    Claiming is the failure mode worth checking: a summary listing six files
    is what an operator trusts, and a missing one is only visible if
    something compares the claim to the disk.
    """

    missing: list[str] = []
    for stage in project.stages:
        target = project.root / STAGE_FILES[stage]
        if stage is Stage.ASSETS:
            if not target.is_dir():
                missing.append(STAGE_FILES[stage])
            continue
        if not target.is_file() or not target.read_text(encoding="utf-8").strip():
            missing.append(STAGE_FILES[stage])

    return {
        "complete": not missing,
        "missing": missing,
        "stages": [stage.value for stage in project.stages],
        "files": list(project.files),
    }


__all__ = [
    "count_substantive_stages",
    "STAGE_FILES",
    "STAGE_ORDER",
    "STAGE_WORDS",
    "ScaffoldedProject",
    "Stage",
    "requested_stages",
    "scaffold_project",
    "slugify",
    "validate_project",
    "wants_whole_project",
]
