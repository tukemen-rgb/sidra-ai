# RUNBOOK: 7B コード特化モデルへの載せ替え（GTX 1660 Ti 6GB）

`docs/RUNBOOK_FIRST_REAL_ANSWER.md` で `qwen2.5:3b-instruct-q4_K_M` が
動いている状態からの**差分**手順。目的はコード生成の質を上げること。
実行するのは社長の PC。**この文書は測っていない数字を書かない。**
数字は全部「あなたの機械で読む」手順として書いてある。

**この文書は載せ替えを勧めていない。**6GB に 7B を載せるのは余裕がなく、
下の算数の結果しだいでは「載せない」が正しい結論になる。判断材料を出すのが
この文書の役目で、判断は社長のもの。

## 0. 先に知っておくこと（ここが全部）

SIDRA は起動時に fail-closed の admission を通る:

```
reviewed manifest → 設定モデルと完全一致 → nvidia-smi で空き VRAM を実測
→ 経路決定 → admitted context cap → adapter → API bind
```

必要 VRAM の式（`models/routing.py`、予約は既定 512 MiB）:

```
必要 = weights_vram_mib + ceil(max_context_tokens / 1000) × kv_cache_mib_per_1k_tokens
判定 = 必要 ≤ (観測した空き VRAM − 512)
```

**通らなければ API のソケットは開かない。**プローブが失敗しても
「6 GiB だろう」と勝手に仮定しない。だから 7B が載らない機械では、
起動が静かに遅くなるのではなく**起動しない**。それが正しい壊れ方。

3B との違いは 1 つだけ: **weights が倍以上になり、6GB では context を
削らないと式が成立しない可能性が高い。**下でそれを確かめる。

## 1. いまの状態を控える（戻せるようにする）

```
ollama list
type .sidra\model-manifest.json
```

この 2 つの出力を**どこかに貼っておく**。戻すのはこの 2 つを元に戻すだけ。
`.sidra\model-manifest.json` は `model-manifest.json.bak` にコピーしておく。

## 2. 空き VRAM を実測する（ゲーム等を閉じてから）

```
nvidia-smi --query-gpu=memory.total,memory.free --format=csv,noheader,nounits
```

左が total、右が free（MiB）。**この free が全ての判断の土台**なので、
ブラウザやゲームを閉じた「普段 SIDRA を使う状態」で測ること。
6GB 機の total は 6144 前後だが、**free はそれよりかなり小さい**のが普通。

以降 `FREE` = いま読んだ free の値。使える上限は `FREE − 512`。

## 3. 量子化を選ぶ（ここが本題）

候補（ollama のタグ。数字は**あなたが手順 4 で読む**）:

| タグ | 位置づけ |
| --- | --- |
| `qwen2.5-coder:7b-instruct-q4_K_M` | 標準。まずこれが載るか見る |
| `qwen2.5-coder:7b-instruct-q3_K_M` | q4 が載らないときの次点。質は落ちる |
| `qwen2.5-coder:3b-instruct-q4_K_M` | 7B を諦める場合。3B のままコード特化にする |

**選び方は好みではなく算数**。手順 4 で SIZE を読み、手順 5 の式に入れる。

## 4. 落として実サイズを読む

```
ollama pull qwen2.5-coder:7b-instruct-q4_K_M
ollama list
```

`ollama list` の SIZE が**ディスク上のサイズ**。VRAM 上の weights は
これより少し大きくなるので、**SIZE を MiB に直して +300 MiB** を
`weights_vram_mib` の出発点にする（安全側に宣言するのが manifest の作法）。

以降 `W` = その値。

## 5. 載るかどうかを決める

context ごとの必要量（`kv_cache_mib_per_1k_tokens` を `K` とする。
7B の K は 3B の 40 より大きい。**手順 7 で実測して確定する**まで、
まず `K = 80` の悲観値で見積もる）:

| context | 必要 VRAM |
| --- | --- |
| 8192 | `W + 8 × K` |
| 4096 | `W + 4 × K` |
| 2048 | `W + 2 × K` |

`FREE − 512` と比べて、**通る一番大きい context を採用する**。

- どれも通らない → **7B q4 は諦める。**手順 3 の表の次の行へ。
- 2048 でしか通らない → **載せない方がよい。**RAG の文脈が 2048 では
  引用が入らず、コードは良くなっても答えが悪くなる。3B のままの方が製品として上。
- 4096 以上で通る → 進んでよい。

> **6GB に 7B は余裕がない。**「動いた」と「使える」は別で、
> context を削って動かした結果 SIDRA の答えが劣化するなら、
> それは載せ替えの失敗であって成功ではない。

## 6. manifest を書き換える

`.sidra\model-manifest.json`。**保存する前に数字を手順 2〜5 と突き合わせる。
この確認行為が「reviewed manifest」のレビューにあたる。**

```json
{
  "version": 1,
  "models": [
    {
      "backend": "ollama",
      "model": "qwen2.5-coder:7b-instruct-q4_K_M",
      "weights_vram_mib": 0,
      "kv_cache_mib_per_1k_tokens": 80,
      "max_context_tokens": 4096,
      "quantization": "q4_K_M",
      "priority": 1,
      "license": "apache-2.0",
      "revision": "<ollama list の ID をここに>"
    }
  ]
}
```

- `weights_vram_mib` の **0 は必ず手順 4 の `W` に置き換える**。0 のままだと
  admission が意味を失う（そして 0 は明らかに嘘なので、書き換え忘れに気づける）。
- `max_context_tokens` は手順 5 で通った値。ここに書いた値が
  そのまま ollama の `num_ctx` になる（`models/http_backends.py`）。
- `model` は `ollama list` の NAME と**完全一致**。1 文字違えば起動しない。

## 7. 起動して、K の悲観値を実測に置き換える

```
set SIDRA_MODEL_BACKEND=ollama
set SIDRA_MODEL_NAME=qwen2.5-coder:7b-instruct-q4_K_M
（以下、RUNBOOK_FIRST_REAL_ANSWER.md の起動手順と同じ）
```

起動したら、**質問を 1 つ投げている最中に**別窓で:

```
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
```

`used − (SIDRA 起動前の used)` が実際の占有。これが
`W + ceil(context/1000) × K` より**小さければ** `K` を実測に近い値へ下げてよい
（下げると context を伸ばせる）。**大きければ manifest の宣言が甘い**ので
`W` か `K` を上げる。宣言は常に実測より安全側に。

## 8. 戻し方

```
set SIDRA_MODEL_NAME=qwen2.5:3b-instruct-q4_K_M
copy .sidra\model-manifest.json.bak .sidra\model-manifest.json
```

これだけ。**重みは消さなくてよい**（消すと戻すのに再 pull が要る）。
ディスクが厳しいときだけ `ollama rm qwen2.5-coder:7b-instruct-q4_K_M`。

載せ替えは manifest と環境変数の 2 か所しか触らないので、
**壊れたら 30 秒で戻せる。**これが「まず試す」を安くしている。

## 9. コード生成の成功率を測る計器（案。実装はしていない）

「コードが良くなった」を感想で言わないための計器。**この項目では実装しない**
（載せ替えを実際にやるまで、測る対象が存在しないため）。

**形**: `scripts/check_code_generation.py`。他の判定器と同じ終了コード
（0=動いた / 1=動かない / 2=悪化 / 3=判定不能）。

**中身**: `src/sidra_ai/evals/code_tasks.py` に小さな課題を 10〜15 問。
1 問 = (依頼文, 実行可能な検査)。例:

```python
CodeTask(
    name="csv-column-sum",
    request="CSV の 3 列目を合計する Python 関数 total(path) を書いて",
    check="assert total(TMP) == 6",   # 固定の一時ファイルを用意して実行
)
```

**採点は実行**。生成されたコードを一時ディレクトリに書き、
**サブプロセスで、ネットワークなしで、タイムアウト付きで**走らせ、
検査が通った数を数える。「それらしい」を数えない。

**数字**: `codegen_pass N/M`（`product_metrics.py` に OUTCOME として登録）。
モデルを変える前後で `--compare` する。

**この計器で気をつけること**:

- **生成コードを本番プロセス内で `exec` しない。**必ず別プロセス・
  一時ディレクトリ・タイムアウト。これは製品の不変条件ではないが、
  自分の足を撃たないための最低線。
- **課題を後から緩めない。**通らなかった問題を書き換えて満点にするのは、
  判定器を持っている意味を消す。落ちた問題は落ちたまま記録する。
- **echo バックエンドでは 0 になる**のが正しい。0 を「測定不能」と
  混同しないよう、モデル未設定なら exit 3 を返す。

実装するかどうかは社長の判断。**7B を実際に載せてからでないと、
この計器は「3B の点数」しか教えない。**

---

**この文書が測っていないこと**: 私は社長の PC の VRAM も、
qwen2.5-coder の実サイズも測っていない。上の表と式は「読み方」であって
「読んだ結果」ではない。数字を埋めるのは手順 2 と手順 4 を実行した人。
