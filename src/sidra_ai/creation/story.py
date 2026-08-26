"""Fill the three written stages with the production's actual parameters.

The scaffolder wrote correct headings and 〔未記入〕 underneath. That is a
worse artifact than it looks: it reads as finished, so nobody notices it says
nothing, and the one thing a scaffolded project could honestly assert - what
the game it ships beside actually does - was left blank.

So the content here is **derived from the artifact, not invented around it**.
The controls table lists the keys ``games.py`` really binds. The difficulty
table carries the real numbers from ``games._DIFFICULTY``, so "hard" in the
document is the same hard the page plays. If a template's parameters change,
these documents change with them; there is no second copy to drift.

Two things are deliberately still blank. The plot and the cast are the
owner's to write, and filling them with generated prose would put invented
material in the one place a reader would take as intent. Blanks are marked so
a reader can tell "for you to fill" from "the generator had nothing to say".

A local model, if there is one, may overlay wording through ``with_prose``.
Nothing here needs it: with no model the documents are still specific, which
is what makes the whole path measurable on a container that has no weights.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.games import TEMPLATES, choose_difficulty, choose_template
from sidra_ai.creation.games import _DIFFICULTY  # noqa: PLC2701 - the real numbers

#: What each template actually binds, read off the template scripts. Kept as
#: data next to the template keys so a new template without an entry is a
#: visible gap rather than a silently generic table.
CONTROLS: dict[str, tuple[tuple[str, str], ...]] = {
    "fishing": (
        ("SPACE", "仕掛けを合わせる"),
        ("クリック / タップ", "同上（ポインタでも同じ操作）"),
    ),
    "catch": (
        ("← →", "受け皿を動かす"),
        ("マウス移動 / ドラッグ", "同上（ポインタでも同じ操作）"),
    ),
}

#: What the two difficulty numbers mean, per template. Without this the table
#: would print two bare floats and call itself a specification.
PARAMETERS: dict[str, tuple[tuple[str, str], ...]] = {
    "fishing": (
        ("マーカー速度", "1 フレームあたりの移動量。大きいほど速い"),
        ("当たり帯の幅", "帯の割合。小さいほど狭い"),
    ),
    "catch": (
        ("落下間隔", "何フレームごとに 1 個落ちるか。小さいほど密"),
        ("受け皿の幅", "画面幅に対する割合。小さいほど狭い"),
    ),
}

def screens(plan: "ProductionPlan") -> tuple[tuple[str, str, str], ...]:
    """The flow the template actually implements, with its real inputs named.

    A screen list naming screens the page does not have would be the same lie
    in a different file, and one that said "操作する" without saying which key
    would be a heading pretending to be a specification.
    """

    keys = " / ".join(key for key, _ in CONTROLS.get(plan.template, ())) or "（未定義）"
    return (
        ("プレイ", "canvas と現在のスコア表示、操作の説明行", f"ページを開いた時点で開始。入力は {keys}"),
        ("結果表示", "スコアと失敗数がプレイ中の画面に出続ける", "リロードでやり直し"),
    )

BLANK = "〔運用者が埋める〕"


@dataclass(frozen=True)
class ProductionPlan:
    """The parameters this production will actually ship with."""

    template: str
    difficulty: str
    speed: float
    band: float

    @property
    def controls(self) -> tuple[tuple[str, str], ...]:
        return CONTROLS.get(self.template, ())

    @property
    def parameters(self) -> tuple[tuple[str, str], ...]:
        return PARAMETERS.get(self.template, ())


def plan_for(request: str) -> ProductionPlan:
    """Read the same request the game generator reads, the same way.

    Calling the generator's own choosers rather than re-implementing them is
    the point: a document derived from a second parser would describe a game
    nobody generated.
    """

    template = choose_template(request)
    difficulty = choose_difficulty(request)
    speed, band = _DIFFICULTY[template][difficulty]
    return ProductionPlan(template, difficulty, speed, band)


def _sources(evidence: tuple[str, ...]) -> str:
    if not evidence:
        return "- （このステージに使える索引の根拠は見つかりませんでした）"
    return "\n".join(f"- {line}" for line in evidence)


def _header(title: str, stage: str, evidence: tuple[str, ...]) -> str:
    return (
        f"# {title} — {stage}\n\n"
        "> SIDRA AI が生成。**数値と操作は同じディレクトリの game.html が"
        "実際に使うもの**で、文章ではなく生成器から引いています。\n\n"
        f"## 根拠にした索引\n\n{_sources(evidence)}\n"
    )


def scenario(title: str, evidence: tuple[str, ...], plan: ProductionPlan) -> str:
    """The one stage that stays mostly blank, and says so.

    An あらすじ is a claim about what the game is about. Generating one would
    hand the owner invented intent in the place they are least likely to
    check it - so the blanks are labelled instead.
    """

    spec = TEMPLATES[plan.template]
    return _header(title, "脚本", evidence) + f"""
## 遊びの芯（テンプレートが決めている部分）

{spec.how_to_play}

この 1 行は生成器の実装から引いています。物語はこの操作の上に載せます。

## あらすじ

{BLANK}（生成器は物語を作りません。上の「遊びの芯」に合う筋を書いてください）

## 登場するもの

| 名前 | 役割 | 見た目のメモ |
|---|---|---|
| 主役 | プレイヤーが動かすもの | {BLANK} |
| 的 | {"合わせる対象（帯の中心）" if plan.template == "fishing" else "落ちてくるもの"} | {BLANK} |

## 場面

1. 開始 — 操作の説明行が出た状態でプレイが始まる
2. 反復 — {"帯に合わせる試行を繰り返す" if plan.template == "fishing" else "落ちてくるものを受け続ける"}
3. 区切り — スコアと失敗数が画面に出続ける（明示的な終了画面は現状なし）
"""


def structure(title: str, evidence: tuple[str, ...], plan: ProductionPlan) -> str:
    rows = "\n".join(
        f"| {name} | {shows} | {advance} |" for name, shows, advance in screens(plan)
    )
    return _header(title, "構成", evidence) + f"""
## 画面フロー

プレイ → 結果表示（同一画面）→ リロードでプレイ

**現状の game.html は単一画面です。**タイトル画面もリザルト画面も無く、
開いた瞬間に始まります。実装に無い画面をここに書けば、この文書は仕様では
なく願望になるので、増やすときは game.html と一緒に増やしてください。

## 各画面

| 画面 | 出るもの | 次へ進む条件 |
|---|---|---|
{rows}

## まだ無いもの（増やすなら実装と同時に）

- タイトル画面（開始ボタン・難易度選択）
- リザルト画面（最終スコア・もう一度）
"""


def features(title: str, evidence: tuple[str, ...], plan: ProductionPlan) -> str:
    """The specification that is actually true of the shipped page."""

    controls = "\n".join(f"| {key} | {does} |" for key, does in plan.controls) or (
        f"| {BLANK} | {BLANK} |"
    )
    names = plan.parameters
    levels = _DIFFICULTY[plan.template]
    if names:
        rows = "\n".join(
            f"| {label} | {levels['easy'][index]} | {levels['normal'][index]} "
            f"| {levels['hard'][index]} |"
            for index, (label, _why) in enumerate(names)
        )
        legend = "\n".join(f"- **{label}**: {why}" for label, why in names)
    else:
        rows = f"| {BLANK} | {BLANK} | {BLANK} | {BLANK} |"
        legend = f"- {BLANK}"
    scoring = (
        "帯の中で合わせられたら 釣果 +1、外したら記録のみ。失敗しても終了しません。"
        if plan.template == "fishing"
        else "受けられたら 受け +1、こぼしたら こぼし +1。どちらも画面に出続けます。"
    )
    return _header(title, "機能設定", evidence) + f"""
## 操作

| 入力 | 動作 |
|---|---|
{controls}

## スコア

{scoring}

## 難易度パラメータ

この依頼は **{plan.difficulty}** で生成されました（speed={plan.speed} / band={plan.band}）。
表の値は `sidra_ai.creation.games` が実際に使う数値です。

| 名前 | easy | normal | hard |
|---|---|---|---|
{rows}

{legend}
"""


def with_prose(document: str, prose: str) -> str:
    """Overlay a model's あらすじ on a document that is already specific.

    Empty input leaves the labelled blank standing: a page that quietly lost
    its "for you to fill" marker would read as finished.
    """

    text = prose.strip()
    if not text:
        return document
    return document.replace(
        f"{BLANK}（生成器は物語を作りません。上の「遊びの芯」に合う筋を書いてください）",
        text,
        1,
    )


__all__ = [
    "BLANK",
    "CONTROLS",
    "PARAMETERS",
    "ProductionPlan",
    "screens",
    "features",
    "plan_for",
    "scenario",
    "structure",
    "with_prose",
]
