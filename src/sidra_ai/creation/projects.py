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

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from sidra_ai.creation.evidence import Fact
from sidra_ai.creation import sprites as sprite_lib
from sidra_ai.creation import story
from sidra_ai.creation.games import generate_game, save_game


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


def _title_from(request: str) -> str:
    """The operator's own words, cut at the making-verb."""

    stripped = re.split(r"を?(?:作って|作成して|生成して|つくって)", request)[0]
    stripped = re.sub(r"(企画から|一連で|一通り|まとめて|だけ)", " ", stripped)
    stripped = " ".join(stripped.split())
    # Removing "企画から" from "釣りゲームを企画から作って" leaves the particle
    # that used to attach to it, and "釣りゲームを" is not a title. Trailing
    # particles are dropped here rather than in the split, because which one
    # is left over depends on which phrase was removed.
    stripped = re.sub(r"[をのはがにで]+$", "", stripped).strip()
    return stripped[:60] or "無題のゲーム"


def _front_matter(title: str, stage: str, evidence: tuple[str, ...]) -> str:
    sources = (
        "\n".join(f"- {line}" for line in evidence)
        if evidence
        else "- （このステージに使える索引の根拠は見つかりませんでした）"
    )
    return f"# {title} — {stage}\n\n> SIDRA AI が生成した骨格です。中身は各ステージの担当が埋めます。\n\n## 根拠にした索引\n\n{sources}\n"


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


def _log_skeleton(title: str, stages: tuple[Stage, ...], evidence: tuple[str, ...]) -> str:
    made = "\n".join(f"- {STAGE_FILES[stage]}" for stage in stages)
    return _front_matter(title, "制作記録", evidence) + f"""
## この回で作ったもの

{made}

## 追記の決まり

生成のたびに「いつ・何を・どの根拠（引用元 path）・どのパラメータで」を 1 行足す。
**索引した文書の中身はここに書かない**（path と日時とパラメータだけ）。
"""


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
    slug = slugify(title, stamp=stamp)
    stages = requested_stages(request)
    evidence = tuple(dict.fromkeys(fact.source for fact in (facts or []) if fact.source))

    # Read once, before any stage is written: every document has to describe
    # the same production, and re-deriving per stage is how two files end up
    # disagreeing about the same game.
    plan = story.plan_for(request)
    # Filled by the assets stage and read by the game stage. Empty when the
    # request asked for a game without assets, which is a supported shape:
    # the page then draws what it always drew.
    asset_paths: dict[str, str] = {}

    root = Path(data_dir) / "artifacts" / "projects" / slug
    root.mkdir(parents=True, exist_ok=True)

    for stage in stages:
        if stage in SKELETONS:
            (root / STAGE_FILES[stage]).write_text(
                SKELETONS[stage](title, evidence, plan), encoding="utf-8"
            )
        elif stage is Stage.ASSETS:
            # Seeded from the request, so regenerating a project gives the
            # same art its own documents already describe.
            written = sprite_lib.save_sprites(
                sprite_lib.generate_sprites(
                    plan.template, seed=sprite_lib.seed_for(request)
                ),
                root / "assets",
            )
            asset_paths = {
                name.removesuffix(".svg"): f"assets/{name}" for name in written
            }
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
                request, evidence=list(evidence) or None, sprites=asset_paths
            )
            (root / "game.html").write_text(game.html, encoding="utf-8")
        elif stage is Stage.LOG:
            (root / STAGE_FILES[stage]).write_text(
                _log_skeleton(title, stages, evidence), encoding="utf-8"
            )

    return ScaffoldedProject(
        slug=slug,
        title=title,
        root=root,
        stages=stages,
        whole_project=wants_whole_project(request),
        evidence=evidence,
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
