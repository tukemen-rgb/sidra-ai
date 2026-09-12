"""A synthesised keydown carries two halves, and they are not the same.

C-1623 found a probe pressing a key no page was listening for: it put the
key into ``code`` as well, so the space bar arrived as ``code: ' '`` - a
code no browser produces - and every template that gates on
``e.code==='Space'`` sat untouched through five thousand frames of
"mashing". C-1626 found the same mistake in eight more places, and in one
of them it had turned into a written conclusion: ``adventure_losable``
recorded that "the sword turned out to be a red herring" from a drive whose
sword was never drawn.

The mistake is invisible from a passing run - the page simply does nothing -
so it is caught here, at the source, across every module that builds one of
these events rather than only the one where it was first found.
"""

from __future__ import annotations

import pathlib
import re

import pytest

#: ``code: k`` / ``code: key`` - the key put where the code belongs - and
#: ``key: code``, the same error the other way round.
_WRONG = re.compile(r"""(code:\s*(?:k|key)\s*[,}])|(key:\s*code\s*[,}])""")

_ROOTS = ("src", "tests", "scripts")


def _sources() -> list[pathlib.Path]:
    here = pathlib.Path(__file__).resolve().parent.parent
    return sorted(
        path
        for root in _ROOTS
        for path in (here / root).rglob("*.py")
        if "__pycache__" not in path.parts
        # This file quotes the mistake on purpose, to prove the scan sees it.
        and path.name != pathlib.Path(__file__).name
    )


def test_the_repository_has_sources_to_scan() -> None:
    """A guard that reads nothing passes for the wrong reason."""

    found = _sources()
    assert len(found) > 100, len(found)


@pytest.mark.parametrize("path", _sources(), ids=lambda p: p.name)
def test_no_synthesised_key_event_puts_a_key_where_the_code_goes(path) -> None:
    text = path.read_text(encoding="utf-8")
    bad = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(text.splitlines(), 1)
        if _WRONG.search(line)
    ]

    assert bad == [], "\n".join(bad)


def test_the_scan_would_catch_the_mistake_it_exists_for() -> None:
    """Both shapes, and the correct one left alone."""

    assert _WRONG.search("fn({ key: key, code: key, preventDefault(){} })")
    assert _WRONG.search("const e = { key: k, code: k, preventDefault(){} };")
    assert _WRONG.search("{ key: code, code: code, clientX: 0 }")
    assert not _WRONG.search(
        "{ key: k === 'Space' ? ' ' : k, code: k === ' ' ? 'Space' : k, }"
    )
    assert not _WRONG.search("{ key: ' ', code: 'Space' }")

# --- C-1651: the scan detects a recurrence; the helper prevents one ----
#
# The scan above works - it caught the same slip twice more in one session
# (C-1645's scene probe, C-1650's ear/eye probe), both of which "worked"
# by luck because adventure listens on ``e.key`` and racing's probe only
# ever pressed ``r``. What it cannot do is stop the next copy being typed,
# because every probe hand-writes the same branch.
#
# ``probekeys`` owns the branch now. These tests hold two things: the
# helper does the pairing correctly when actually run, and the number of
# places still writing it by hand may fall but never rise - so a new probe
# cannot add one.

#: A key paired with ``'Space'`` by hand: either the literal code, or the
#: ``k === ' ' ? 'Space'`` branch under any variable name.
_BY_HAND = re.compile(
    r"""code\s*:\s*(?:'Space'|"Space"|[A-Za-z_$][\w$]*\s*===?\s*' '\s*\?\s*'Space')"""
)

#: Files that own the pattern rather than copy it.
_OWNS_IT = ("probekeys.py", pathlib.Path(__file__).name)

#: Measured 2026-09-11 (C-1651), after migrating the two probes the
#: recurrence happened in. The bulk migration is C-1654; until then this
#: number is the ratchet. **It may be lowered, never raised** - a new
#: probe that hand-writes the branch has to fail here rather than wait to
#: be found by the scan above after it has already gone wrong once.
#:
#: C-1654 第 1 陣 (2026-09-11): adventure と racing の 18 か所を移して 128 -> 110.
#:
#: 128, not the 127 first recorded: that number was measured at 01:13 and
#: two more probes landed from other loops while this was being verified,
#: so it was already stale when it merged and turned this test red on
#: main. The count at the parent of the merge was 130 and this change
#: took it to 128. Corrected against the tree it actually merged onto -
#: a constant measured on a tree that no longer exists is not a ratchet,
#: it is a guess. Raising it needs that kind of reason in writing;
#: "a new probe needed one" is not one.
#: C-1654 第 2 陣 (2026-09-11): kaiju・platformer・duel の 27 か所を移して
#: 109 -> 82. **項目が書いていた「kaiju 13 / platformer 11 / duel 9 の 33 か所を
#: 機械的に」は誤りだった**——正準形（第 1 陣の形）はそのうち 15 か所だけで
#: (kaiju 11・platformer 4・duel 0)、残りは 4 つの別の形だった。形ごとに規則を
#: 書き、**認識できない形は触らない**ようにしたので、動いた数がそのまま
#: 「機械的に移せた数」になる。残る 6 か所（kaiju 1・platformer 3・duel 2)は
#: どの規則にも当てはまらず、手で読む必要があるので次の陣へ回した。
#:
#: **正しさの根拠は 51 本の probe の出力が移行前後でバイト単位で同一**である
#: こと。probeKey は 'Space' を ' ' へ写すが正準形の literal は写さないので、
#: k === 'Space' で両者は食い違う——第 1 陣が無事だったのは「その呼び出し側が
#: 'Space' を渡さない」という**実測の事実**であって置換の性質ではない。だから
#: 陣ごとに測り直す。
#:
#: ファイル数は 32 が実測値（33 は 1 つ古かった）。
#: C-1654 第 3 陣 (2026-09-11): 規則に当てはまらなかった 6 か所を手で読んで移し、
#: 82 -> 76（ファイル 32 -> 29）。5 か所は形が違うだけ（kaiju の `kKey`、
#: platformer の `kd`/`ku`、duel の `down`/`up`）で、`kd`/`ku` が `{key: k}` 形でも
#: 安全なのは**呼び出し側が ' ' しか渡さないことを読んで確かめた**から。
#:
#: 6 つ目（platformer `PAN_PROBE` の `ev`）だけは**別の構造**だった——
#: `stopImmediatePropagation` に**中身**があり `if (stopped) break` がそれを見る。
#: 共有ヘルパのそれは空なので、鍵と code の対応だけ `probeKey` から取り、
#: **止める振る舞いは明示的に横へ書いた**。
#:
#: **ただし「機械的に置換していたら壊れていた」とは書けない**——その明示行を
#: 外して 51 本を測り直すと**出力は 1 本も変わらなかった**。ページ自身は
#: `stopImmediatePropagation` を 10 か所で呼ぶが、この probe が送る鍵の経路では
#: 早期 break が観測に出ない。**つまりこのラチェットと probe 比較は、この種の
#: 取り違えを捕まえられない**。残したのは「コードが言っていることを変えない」
#: ためであって、実測された破損を防いだからではない。
#: C-1654 第 4 陣 (2026-09-12): marble・shooter・round・catchgame・puzzle・
#: fishing の 38 か所を移して 76 -> 38（ファイル 29 -> 23）。**この 6 つで
#: 該当箇所はゼロになった**——残る 38 は 17 のモジュールに 1〜4 か所ずつ散った
#: 尾で、テンプレート本体ではない。
#:
#: 形は 4 つに分かれ、**分類してから触った**（第 2 陣の「一括で機械的に」が
#: 誤りだった反省）: 正準形 25・すでに probeKey と同一の折り畳み済み 4・
#: 止める ev 6・変数を取らない固定 literal 3。止める 6 か所は第 3 陣の
#: platformer `PAN_PROBE` と同じ構造なので、**対応だけ probeKey から取り、
#: 止める振る舞いは横に明示**した。各規則は「この形が何か所あるはず」を
#: 先に書き、数が合わなければ**書き換えずに停止**する。
#:
#: **'Space' の食い違いは実測で潰した**——probeKey は 'Space' を ' ' へ写すが
#: 正準形の literal は写さないので、k === 'Space' で両者は食い違う。この 6
#: モジュールの呼び出し側を全部読み、'Space' を鍵として渡す箇所が 1 つも
#: 無いことを確かめた。`hold=` 経由で hKey/tkPress に届く値も、実在する
#: 呼び出しは ' '・矢印キー・'x'・'j'・''・None だけ。
#:
#: **正しさの根拠は 127 本の probe 駆動の出力が移行前後でバイト単位で同一**
#: であること（6 モジュール分に加え、round は共有なので 9 テンプレートの
#: ページそれぞれに対して駆動した）。rc・stdout・stderr の 3 つとも一致。
#:
#: **第 3 陣が「機械的に置換していたら壊れていたとは書けない」と記録したが、
#: 第 4 陣では書ける**——明示した止める行を外して 127 本を測り直すと
#: **2 本が変わった**（fishing・puzzle の `pan_probe`）。止めを無視すると
#: 開始画面のリスナーが止めたはずの鍵がページまで届き、測る窓の**手前**で
#: 音が 1 つ鳴る: `before` 0 -> 1、`pans` の先頭に余分な 1 件（fishing は
#: `casts` 2 -> 3 も）。これは既存の `test_creation_sfx_pan` の
#: `assert got["before"] == 0` に当たるので、**この種の取り違えはここでは
#: 目に見えず通り抜けはしない**。第 3 陣の「捕まえられない」は platformer の
#: `PAN_PROBE` 1 件について測った事実であって、ラチェット全体の性質では
#: なかった——その記述の射程をここで狭める。
#: C-1654 第 5 陣 (2026-09-12): 残る尾 36 か所を 22 ファイルから移して
#: 38 -> 2（ファイル 23 -> 2）。**これで移せるものは全部移した**。
#:
#: 形は 6 つ: 正準形 15・inline の forEach 5・すでに折り畳み済み 3・
#: 止める `ev` 4・変数を取らない固定 literal 8・押した位置を足す 1
#: （combo の pad press。`probeKey` は鍵と code しか対にしないので、
#: `clientX`/`clientY` は横に明示して残した）。第 4 陣と同じく、規則ごとに
#: 「この形が何か所あるはず」を先に宣言し、合わなければ書き換えずに停止する。
#:
#: **`'Space'` を鍵として渡す呼び出しがこの陣で初めて出た**——combo の
#: `press('Space')` が 2 か所。ただしその場所は**もともと折り畳んでいる**形
#: （`key: code === 'Space' ? ' ' : code`）で probeKey と同一なので安全。
#: 残りの呼び出し側も全部読み、`hold=` 経由で届く実在の値は ' '・矢印キー・
#: 'x'・'j'・''・None だけだった。
#:
#: **残る 2 つは移さない。どちらも動かせない理由がある**:
#:
#: 1. `creation/focus.py` の `focusRelease` は、1 文字キーを `'KeyX'` へ写す
#:    ——`probekeys` の scope note が「鍵から導けない code（`'KeyR'`・pad の表・
#:    remap の意図的な不一致）は持ち込まない」と明記している対象そのもの。
#: 2. `tests/test_creation_mash_probe.py` の 1 件は**コードではなく散文**で、
#:    docstring がこの形を引用しているだけ。走査はそれを見分けない。
#:
#: つまり**この数は 0 にはならない**。2 が床であり、下げるには走査の側を
#: 変えるしかない——それは移行ではなく別の判断なので、ここではやらない。
#:
#: **正しさの根拠**: 163 本の probe 駆動のうち **157 本が移行前後でバイト単位で
#: 同一**。残る 6 本（attract・audio の `probe_source` × 3 テンプレート）は
#: **コードを変えずに 2 回走らせても違う**——ページが乱数で決める値を読むので、
#: バイト比較ではもともと何も言えない。その 6 本については float を正規化して
#: 比べ、audio の 3 本は完全一致、attract の 3 本は `idle`（誘い画面の描画
#: ハッシュ列）以外の全フィールドが一致した。**`idle` については この方法は
#: 何も保証しない**ことを記録しておく。
#: probe builder を持たない 2 つは別に実測した: `evals/race_rungs` の
#: `evaluate_race_rungs()` と、判定器自身の `_FISHING_DRAW_PROBE` は
#: どちらも移行前後で出力が完全一致。
_HAND_ROLLED_SITES = 2
_HAND_ROLLED_FILES = 2


def _hand_rolled() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _sources():
        if path.name in _OWNS_IT:
            continue
        found = sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                    if _BY_HAND.search(line))
        if found:
            counts[str(path)] = found
    return counts


def test_the_ratchet_only_turns_one_way() -> None:
    counts = _hand_rolled()
    sites, files = sum(counts.values()), len(counts)

    assert sites <= _HAND_ROLLED_SITES, (
        f"a new probe wrote the key/code branch by hand ({sites} sites, was "
        f"{_HAND_ROLLED_SITES}). Embed probekeys.KEY_EVENT_SLOT and call "
        f"probeKey(k) instead:\n" + "\n".join(f"  {k}: {v}" for k, v in counts.items())
    )
    assert files <= _HAND_ROLLED_FILES, (sites, files)


def test_the_ratchet_is_not_already_stale() -> None:
    """A number left far above the truth would let several new copies in
    before anybody noticed."""

    sites = sum(_hand_rolled().values())

    assert sites >= _HAND_ROLLED_SITES - 5, (
        f"{_HAND_ROLLED_SITES - sites} sites were migrated without lowering "
        f"the ratchet to {sites}"
    )


def test_the_two_probes_the_slip_recurred_in_use_the_helper() -> None:
    from sidra_ai.creation.adventure import SCENE_ORDER_PROBE
    from sidra_ai.creation.probekeys import KEY_EVENT_SLOT
    from sidra_ai.creation.racing import EAR_EYE_PROBE

    for name, source in (("scene order", SCENE_ORDER_PROBE), ("ear/eye", EAR_EYE_PROBE)):
        assert KEY_EVENT_SLOT in source, name
        assert not _BY_HAND.search(source), name


def test_the_helper_pairs_the_halves_the_way_a_browser_does() -> None:
    """Run it, rather than read it: this is the one branch the repository
    has got wrong four times."""

    import json
    import subprocess

    from sidra_ai.creation.probekeys import KEY_EVENT_JS

    source = KEY_EVENT_JS + """
const seen = {};
for (const k of [' ', 'Space', 'r', 'ArrowLeft']) {
  const e = probeKey(k);
  seen[k] = [e.key, e.code, typeof e.preventDefault, typeof e.stopImmediatePropagation];
}
console.log(JSON.stringify(seen));
"""
    run = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr[:300]
    seen = json.loads(run.stdout.strip().splitlines()[-1])

    # Both spellings of the space bar give what a browser sends, so a probe
    # cannot get the halves the wrong way round by writing the argument the
    # other way - which is how C-1650 went wrong.
    assert seen[" "][:2] == [" ", "Space"]
    assert seen["Space"][:2] == [" ", "Space"]
    # ...and an ordinary key is untouched.
    assert seen["r"][:2] == ["r", "r"]
    assert seen["ArrowLeft"][:2] == ["ArrowLeft", "ArrowLeft"]
    for entry in seen.values():
        assert entry[2:] == ["function", "function"], entry


def test_the_helper_declares_what_it_introduces() -> None:
    """The same contract the animation preamble keeps: a probe that already
    had a ``probeKey`` would be shadowed silently otherwise."""

    from sidra_ai.creation.probekeys import KEY_EVENT_JS, KEY_EVENT_NAMES

    declared = {f"function {name}(" for name in KEY_EVENT_NAMES}
    defined = set(re.findall(r"function\s+(\w+)\s*\(", KEY_EVENT_JS))

    assert defined == set(KEY_EVENT_NAMES), (defined, KEY_EVENT_NAMES)
    for text in declared:
        assert text in KEY_EVENT_JS
