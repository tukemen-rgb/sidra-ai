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
from html import escape

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
    "adventure": (
        ("矢印 / WASD", "勇者を動かす"),
        ("SPACE / タップ", "剣を振る（草を刈る・敵を倒す・調べる）"),
        ("R", "やられた後にやり直す"),
    ),
    "duel": (
        ("SPACE / 長押し", "チャージして、離すとビーム発射"),
        ("↑ ↓", "レーンを移動してかわす"),
        ("SPACE 連打", "押し合いで押し返す"),
    ),
    "shooter": (
        ("← →", "自機を左右に動かす"),
        ("SPACE / 長押し / タップ", "連射する"),
        ("R", "撃墜された後にやり直す"),
    ),
    "puzzle": (
        ("← ↑ → ↓", "カーソルを動かす"),
        ("SPACE / タップ", "同じ色のかたまりを消す（2 個以上）"),
        ("R", "盤面をやり直す"),
    ),
    "kaiju": (
        ("← →", "多脚戦車を歩かせる（地割れから離れる）"),
        ("SPACE / タップ", "撃つ。脚を撃ち抜くと頭が下りてくる"),
        ("R", "退いた後にやり直す"),
    ),
    "marble": (
        ("← →", "玉を左右に寄せる（ゲートの中央へ）"),
        ("R / タップ", "転倒やゴールのあとにやり直す"),
    ),
    "racing": (
        ("← →", "ハンドルを切る（車を左右へ）"),
        ("R", "ゴール後や事故のあとに走り直す"),
    ),
    "platformer": (
        ("← →", "走る"),
        ("↑ / SPACE / タップ", "ジャンプ。押す長さで高さが変わる"),
        ("R", "コースをはじめからやり直す"),
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
    "adventure": (
        ("敵の速さ", "1 フレームあたりの移動量。大きいほど速い"),
        ("敵の数", "洞窟に出る敵の数。祭壇はこれより 1 少ない"),
    ),
    "duel": (
        ("相手のチャージ速度", "倍率。大きいほど太いビームが早く来る"),
        ("相手の思考間隔", "何フレームごとに動きを決めるか。小さいほど賢い"),
    ),
    "shooter": (
        ("降下速度", "1 フレームあたりの落下量。大きいほど早く迫る"),
        ("波の間隔", "何フレームごとに 1 波来るか。小さいほど密"),
    ),
    "puzzle": (
        ("色の数", "盤面に出る色数。多いほどかたまりが小さくなる"),
        ("盤面の幅", "横のマス数。広いほど手が長く続く"),
    ),
    "kaiju": (
        ("地割れの開く速さ", "1 フレームあたりの拡がり。大きいほど逃げる猶予が短い"),
        ("脚の耐久", "1 周期で脚に必要な命中数。多いほど頭が下りるまで長い"),
    ),
    "marble": (
        ("転がる速さ", "1 フレームあたりの前進量。大きいほどゲートの判断が速くなる"),
        ("ゲートの広さ", "通過と見なす左右の幅。狭いほど寄せが正確でないと抜けない"),
    ),
    "racing": (
        ("走行速度", "1 フレームあたりの前進量。大きいほど 1 周が速く、操作も忙しい"),
        ("障害物の間隔", "コース距離いくつごとに置くか。小さいほど密"),
    ),
    "platformer": (
        ("隙間の倍率", "足場の間の距離に掛かる係数。大きいほど跳びが際どい"),
        ("足場の数", "コースの長さ。多いほどゴールが遠い"),
    ),
}

#: The same key, written for a reader of English (C-1942).
#:
#: Keyed by the key string itself rather than by template, because the same
#: key appears in up to four templates and a per-template copy would be four
#: places to forget. What it is NOT is a second table of controls: the
#: *meaning* column stays where it is, and the check below makes a missing
#: entry impossible to ship rather than something a reader notices later - a
#: copied table is the one that goes stale (C-1848, C-1850).
#:
#: The arrow and letter keys are the same glyphs in both languages and are
#: listed anyway: leaving them out would make "not in the table" mean two
#: different things.
KEY_EN: dict[str, str] = {
    "SPACE": "SPACE",
    "R": "R",
    "← →": "← →",
    "↑ ↓": "↑ ↓",
    "← ↑ → ↓": "← ↑ → ↓",
    "クリック / タップ": "click / tap",
    "マウス移動 / ドラッグ": "mouse move / drag",
    "矢印 / WASD": "Arrows / WASD",
    "SPACE / タップ": "SPACE / tap",
    "SPACE / 長押し": "SPACE (hold)",
    "SPACE 連打": "SPACE (mash)",
    "SPACE / 長押し / タップ": "SPACE / hold / tap",
    "R / タップ": "R / tap",
    "↑ / SPACE / タップ": "↑ / SPACE / tap",
}

#: Derived from ``CONTROLS`` rather than counted by hand: a template added
#: with a key nobody translated raises here, at import, instead of shipping a
#: Japanese key inside an English document.
_MISSING_KEY_EN = sorted(
    {key for rows in CONTROLS.values() for key, _does in rows} - set(KEY_EN)
)
if _MISSING_KEY_EN:  # pragma: no cover - the whole point is that it never runs
    raise RuntimeError(
        f"story.KEY_EN has no English for {_MISSING_KEY_EN}; "
        "every key in CONTROLS needs one before a document can be written "
        "in English"
    )


def english_key(key: str) -> str:
    """One control key, for a document written in English."""

    return KEY_EN[key]


def screens(
    plan: "ProductionPlan", *, in_japanese: bool = True
) -> tuple[tuple[str, str, str], ...]:
    """The flow the template actually implements, with its real inputs named.

    A screen list naming screens the page does not have would be the same lie
    in a different file, and one that said "操作する" without saying which key
    would be a heading pretending to be a specification.

    C-1848: and the same lie in reverse. This listed two rows - play and the
    score strip - and the prose below called the page single-screen with no
    title and no result screen, which stopped being true when C-1033 gave every
    template a briefing gate, recap gave it a result strip, and attract gave it
    a demo. Measured across all ten: every one has all three. A reader planning
    from this document would have built a start screen that was already there.
    #
    The rows are assembled from the modules that own those features rather than
    from a list here, because a list here is exactly what went stale.
    """

    from sidra_ai.creation import attract, recap, startscreen

    bound = [key for key, _does in CONTROLS.get(plan.template, ())]
    if in_japanese:
        keys = " / ".join(bound) or "（未定義）"
    else:
        # The key itself is translated too (C-1942): 「SPACE / タップ」 inside
        # an English sentence is the one-word-of-another-language case §37 is
        # about, and here there is no reason for it - the page binds a tap,
        # and "tap" is the word for it.
        keys = " / ".join(english_key(key) for key in bound) or "(undefined)"
    rows: list[tuple[str, str, str]] = []

    briefing = startscreen.BRIEFINGS.get(plan.template, ())
    if briefing and in_japanese:
        rows.append((
            "開始（ブリーフィング）",
            "狙いと操作を書いた " + str(len(briefing)) + " 行と、開始待ちの案内",
            "キー入力かタップで開始（この操作で音も有効になる）",
        ))
    elif briefing:
        rows.append((
            "Start (briefing)",
            f"{len(briefing)} lines saying what to aim for and how to play, "
            "and the prompt that waits for you",
            "any key or a tap starts it (that same input is what enables sound)",
        ))
    if in_japanese:
        rows.append(
            ("プレイ", "canvas と現在のスコア表示、操作の説明行", f"入力は {keys}")
        )
    else:
        rows.append((
            "Play",
            "the canvas, the running score, and the line that names the controls",
            f"input is {keys}",
        ))
    if plan.template in recap.LOSS_WIRED:
        rows.append((
            "結果表示（負け）",
            "スコアと、負けた原因を数えた帯（0 回の原因は出さない）",
            "R / タップでもう一度",
        ) if in_japanese else (
            "Result (loss)",
            "the score, and a strip counting what actually beat you "
            "(a cause with a count of 0 is not shown)",
            "R / tap to play again",
        ))
    else:
        rows.append((
            "結果表示",
            "スコアと失敗数がプレイ中の画面に出続ける（負けで終わる状態はこの型には無い）",
            "リロードでやり直し",
        ) if in_japanese else (
            "Result",
            "the score and the miss count stay on the playing screen "
            "(this kind has no state that ends in a loss)",
            "reload to start over",
        ))
    if plan.template in attract.ATTRACT_TEMPLATES:
        rows.append((
            "アトラクト（放置デモ）",
            "誰も触っていない間、ページが自分で動いて見せる",
            "入力があれば開始画面に戻る",
        ) if in_japanese else (
            "Attract (idle demo)",
            "while nobody is touching it, the page plays itself to show what it is",
            "any input returns to the start screen",
        ))
    return tuple(rows)

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


def _sources(evidence: tuple[str, ...], in_japanese: bool = True) -> str:
    if not evidence:
        return (
            "- （このステージに使える索引の根拠は見つかりませんでした）"
            if in_japanese
            else "- (no indexed source was found for this stage)"
        )
    # Source labels are the path of an indexed Issue/PR body (EXTERNAL trust):
    # escape them so HTML in a label is displayed, not executed, when the .md is
    # opened in a Markdown renderer that permits inline HTML (C-1486, the projects
    # twin of the document C-1483).
    return "\n".join(f"- {escape(line, quote=False)}" for line in evidence)


def _header(
    title: str,
    stage: str,
    evidence: tuple[str, ...],
    fallback: str = "",
    *,
    in_japanese: bool = True,
) -> str:
    # The title comes from the request; escape it in the heading for the same
    # reason (C-1486). The stored .title stays raw for the chat summary.
    #
    # C-1790: when the request named a genre we cannot build, every design doc
    # describes the default template under the asked-for title, so each one has
    # to admit the swap - not only production-log.md (C-1605). The wording is the
    # single source used by the log, the game page (C-1788) and the chat summary
    # (C-1285); a buildable genre passes "" and draws no note.
    #
    # C-1942: ``in_japanese`` is the language of the *document*, and only
    # ``structure`` passes anything but the default. The other two are filled
    # from the template registry, which holds how_to_play and the control
    # meanings in Japanese alone, so an English frame around them would be
    # the half-translated document this loop has refused five times.
    # .strip() on the fallback because its English form carries a leading
    # space - it is written to be appended after a chat sentence, and here it
    # opens a quoted line. Byte-identical for the Japanese one.
    swap = f"> ⚠️ {escape(fallback.strip(), quote=False)}\n\n" if fallback else ""
    if in_japanese:
        provenance = (
            "> SIDRA AI が生成。**数値と操作は同じディレクトリの game.html が"
            "実際に使うもの**で、文章ではなく生成器から引いています。"
        )
        sources_heading = "## 根拠にした索引"
    else:
        provenance = (
            "> Generated by SIDRA AI. **The numbers and the controls are the "
            "ones game.html in this same directory actually uses** - they are "
            "read off the generator, not written up beside it."
        )
        sources_heading = "## Sources indexed"
    return (
        f"# {escape(title, quote=False)} — {stage}\n\n"
        f"{provenance}\n\n"
        f"{swap}"
        f"{sources_heading}\n\n{_sources(evidence, in_japanese)}\n"
    )


def scenario(
    title: str, evidence: tuple[str, ...], plan: ProductionPlan, fallback: str = ""
) -> str:
    """The one stage that stays mostly blank, and says so.

    An あらすじ is a claim about what the game is about. Generating one would
    hand the owner invented intent in the place they are least likely to
    check it - so the blanks are labelled instead.
    """

    spec = TEMPLATES[plan.template]
    return _header(title, "脚本", evidence, fallback) + f"""
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


def structure(
    title: str,
    evidence: tuple[str, ...],
    plan: ProductionPlan,
    fallback: str = "",
    *,
    in_japanese: bool = True,
) -> str:
    """The screen list, in the language the request was written in.

    C-1942. This is the first of the three design documents to follow the
    request's language, and it is first because of what fills it: its rows
    are this module's own prose plus the **keys** ``CONTROLS`` binds - not
    the meanings beside them, not ``how_to_play``, not the parameter labels.
    Those are Japanese product data, which is why ``scenario`` and
    ``features`` are still written in Japanese whatever the request said. A
    document does not change language in the middle of itself, so they wait
    for the registry rather than get an English frame over Japanese rows.
    """

    flow = screens(plan, in_japanese=in_japanese)
    rows = "\n".join(
        f"| {name} | {shows} | {advance} |" for name, shows, advance in flow
    )
    arrow = " → ".join(name for name, _shows, _advance in flow)
    if in_japanese:
        return _header(title, "構成", evidence, fallback) + f"""
## 画面フロー

{arrow}

実装に無い画面をここに書けば、この文書は仕様ではなく願望になります。
**逆も同じで、ある画面を無いと書けば、読んだ人は既にある物を作り直します。**
上の並びと下の表は、画面を実装している側の表から組み立てています——
画面が増えればここも増え、減ればここからも消えます。

## 各画面

| 画面 | 出るもの | 次へ進む条件 |
|---|---|---|
{rows}

## まだ無いもの（増やすなら実装と同時に）

- 開始画面での難易度選択（難易度は依頼の言葉で決まり、画面からは選べません）
- 通しの進行（面の連なり・セーブ）
"""
    return _header(
        title, "Structure", evidence, fallback, in_japanese=False
    ) + f"""
## Screen flow

{arrow}

A screen written here that the build does not have turns this document from
a specification into a wish.
**The reverse costs the same: call an existing screen missing and whoever
reads this will build a second one.**
The order above and the table below are assembled from the modules that
implement those screens - add a screen and it appears here, remove one and
it disappears from here too.

## Each screen

| Screen | What is on it | How you move on |
|---|---|---|
{rows}

## Not there yet (add it to the build and to this list together)

- choosing the difficulty on the start screen (the difficulty comes from the
  words of the request; the screen cannot set it)
- progression across a session (levels in sequence, saving)
"""


def features(
    title: str, evidence: tuple[str, ...], plan: ProductionPlan, fallback: str = ""
) -> str:
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
        "帯の中で合わせたら 得点 +1、濃い中央で合わせたら会心で +2。外したら記録のみ。失敗しても終了しません。"
        if plan.template == "fishing"
        else "受けられたら 受け +1、こぼしたら こぼし +1。どちらも画面に出続けます。"
    )
    return _header(title, "機能設定", evidence, fallback) + f"""
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
