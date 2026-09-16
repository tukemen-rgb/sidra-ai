# GDP（ChatGPT）向け引き継ぎ — SIDRA AI の現状と連携の仕方

2026-09-16 作成。読み手は **GDP（ChatGPT / Codex）**。社長の指示「ChatGPT にも協力
して作ってもらいたい」に応えて、**いま何がどこまで出来ていて、どこで・どう手を
出せば実測で前進するか**を 1 枚にした。数字はすべてこの日に実走して得たもの。
規則の正本は `docs/COLLABORATION.md`（英語本文が規範）と Issue #372 本文。

## 1. 5 分で読む現状（2026-09-16 実測、main `551c22d`）

| 検査 | 何を確かめるか | 結果 |
|---|---|---|
| `python -m pytest` | 製品全体の回帰 | 8201 passed / 6 skipped / 0 failed |
| `scripts/verify_gate_recall.py` | 秘密・個人情報・注入を関門が捕まえ、普通の文を誤検知しない | PASSED（捕まえる 20 / 無視する 9） |
| `scripts/check_answerable_regression.py`（BM25） | 語彙一致だけでどこまで答えられるか | 15/38（直接 13/18・言い換え 2/20・弁別 +26.3・MRR 0.289） |
| 同（e5 再ランク） | 意味検索を足した実運用構成 | 19/38（直接 13/18・言い換え 6/20・弁別 +34.2・MRR 0.346） |
| `scripts/product_metrics.py` | 外から見える 564 指標 | 0 件がゼロ |
| スマホ実走（iPhone 14 / Pixel 7 viewport） | 実 UI で質問して回答が出るか | 横はみ出し 0px・48px 未満の操作部 0 |

言葉にすると: **安全側（関門・read-only・外部 API ゼロ）は固まっていて、製品は
5 リポジトリの実文書に対して 38 問中 19 問に出典付きで答えられる。** 残り 19 問が
「理想との差」で、内訳は次のとおり。

- **直接語の質問 5 問**（`submission-fee` / `cy-mvp-scope` / `cy-payments` /
  `mkt-what-is-this-repo` / `gp-unity-webgl-compression`）。索引に語そのものが
  無い。**文書側が書いていない**か、書き方が質問と噛み合っていない。
- **言い換えの質問 14 問**。埋め込みモデル 3 種（e5-small / ruri-v3-30m /
  e5-base）で**同じ問が落ちる**ことを実測済みで、律速は再ランクではなく
  **候補生成（BM25、文字 bigram 索引）側**。測って却下した手: 係数 k1/b、
  一次段の意味検索、センタリング、PRF/クエリ拡張、混合 bigram の減点、
  形態素解析器（Janome。候補窓 200 では効果消失）。詳細は
  `docs/research/perf-competitive-2026-09-08.md` と `docs/OUTCOMES.md`。

問の名前と本文は `src/sidra_ai/evals/outcome_questions.py`。**この文書には
質問文も答えの marker も書かない**（`docs/` は索引対象で、書くとこの文書自身が
その問の rank 1 に化ける——2026-08-23 に一度やった事故）。

## 2. GitHub の連携先

| 連携先 | 何に使う | 備考 |
|---|---|---|
| `https://github.com/tukemen-rgb/sidra-ai`（**公開**） | 本体。既定ブランチは `main`。Claude の自動ループは main へ直接 push する | 認証無しで読める |
| **Issue #372「AI Review Board — GDP × Claude 連携窓口」** | GDP の提案・異議・数字の解釈をコメントで出す場所。Claude のループが起動のたびにコメント総数を見て、増えていれば読む | 最終コメント 2026-08-24（13 件）。それ以降止まっている |
| 他 4 リポジトリの **Issue #1**（site / creater-yard / Fg / marketing、いずれも**非公開**） | それぞれの AI Review Board | GDP が読むには社長の GitHub 連携で該当リポジトリを許可する必要がある |
| `.github/workflows/integration-v01.yml` | push / PR で走る門: 固定バージョン検査・外部 LLM SDK の拒否・全 pytest | 赤のまま main に入れない |
| `.githooks/pre-push`（`git config core.hooksPath .githooks` で有効化） | push 直前の門: 衝突マーカー・板の整合 | `bash scripts/check_before_push.sh` でも直接走る |
| `docs/BACKLOG.md` | 作業キュー。`→ 動かす数字:` 付きの項目をループが 1 件ずつ取る。**E 節**が社長判断待ち（2026-09-16 時点 12 件） | GDP の数字付き提案はループがここへ翻訳する |
| `docs/LOOP_LOG.md` | ループの痕跡（起動・結果・実測）。末尾が最新 | 「誰が何をしたか」はここと git log が正 |

**ChatGPT 側で要る設定（社長の作業）**: ChatGPT の GitHub 連携（Codex または
コネクタ）で `tukemen-rgb/sidra-ai` を許可する。sidra-ai は公開なので URL を渡す
だけでも読める。非公開 4 本を読ませるなら、それぞれを明示的に許可する。
**トークンやパスワードは ChatGPT にも Issue にも貼らない**（不変条件 5）。

**読む順**（初回、合計 30 分）: `README.md` → `docs/COLLABORATION.md` →
`docs/SECURITY.md` → `docs/OUTCOMES.md` → `docs/BACKLOG.md` の先頭〜「完了条件」と
E 節 → `docs/LOOP_LOG.md` の末尾 200 行 → Issue #372 の全コメント。

**古い文書に注意**: `docs/LANES.md`（2026-08-15）の「6 レーン・Draft PR・ベース
ブランチ `claude/sidra-ai-gdp-qecrab`」は**現行の運用ではない**。レーンの
ブランチは remote に存在せず、ループは main へ直接 push している。8/18 の
Draft PR 10 件（#360〜#370）も同じ運用の名残で、取り込まれていない。

## 3. 決まりごと（Issue #372 本文と `docs/BACKLOG.md` 厳守事項の要約）

1. **1 コメント = 1 論点。** 提案には**動かしたい数字**を書く
   （例: `answerable paraphrase 6/20 を上げたい`）。数字の無い提案は E 節
   （社長判断待ち）へ回る。
2. 事実は `docs/OUTCOMES.md` / `docs/BACKLOG.md` / `docs/SECURITY.md` と実測を正と
   する。**推測で数字を書かない。** SIDRA での改善主張は判定器の終了コード
   （`--compare`: 0 前進 / 1 不動 / 2 後退）と実測値だけで決める。
3. 不変条件に触れる提案は自分で「要判断」と明記する。不変条件は:
   GitHub は read-only／外部 LLM API・有料 API を使わない／待ち受けは
   loopback 既定／秘密・個人情報をどこにも書かない／本番 deploy をしない／
   GAMEYARD・CreatorYard 本体を変更しない／他 AI の成果物を理由なく削除しない。
4. 「他の AI が作業した」と言うのは、対応するコミット・PR・成果物が実在する
   ときだけ。取り込みの前に差分・試験・安全性・重複実装・方針整合を確認する。
5. **どの AI が出したかに関係なく、良い実装が勝つ。**

## 4. いま GDP の力が効く論点

GDP の役割は Issue #372 本文どおり「戦略・製品観点のレビューと提案。優先順位への
異議。数字の解釈への突っ込み」。実装はループが行うので、**提案は数字付きで、
根拠と検証手順まで書く**と最短で回る。

1. **言い換え 14 問の壁（候補生成側）。** 文字 bigram 索引には「語」が無い
   （断片 `者が` の idf 3.20 > `制作` 2.96 という実測）。語の単位を持つ索引を
   足す案（形態素解析器は E 節で「要判断」、Janome 実測は候補窓 200 で効果
   消失）に対し、**別の切り口**（例: 文書側の見出し・要約行の整備、質問の型
   ごとの索引フィールド、同義語の文書内併記）を数字付きで。ただし「答案を
   索引に置く」形は禁止（§1 末尾）。
2. **直接語の 5 問は文書の問題。** 対象リポジトリの文書に該当する記述が無いか
   薄い。GDP が各 Review Board（Issue #1）で**文書側の加筆**を提案すれば、
   SIDRA 側は変更無しで動く。2026-08-23 の `docs/DESIGN.md` §9 日本語アンカーの
   依頼と同じ型。
3. **E 節の 12 件の要判断。** 社長が決める領域だが、GDP の推奨と根拠が付くと
   決めやすい。特に「言い換えの弱さに形態素解析器を入れるか」「`answerable`
   の marker は完全一致 1 本でよいか」「PII 検疫が答えを持つ文書を索引から
   外している」「ストリーミングと出力ガードの衝突」。
4. **Issue #372 で止まっている問い（2026-08-24）**: 網の要る数字
   （`github_documents_indexed` など）はどの判定器が「完了」を決めるのか。
   (a) 一般化 / (b) `github_*` を列挙 / (c) 現状維持。GDP の推奨が付けば社長が
   決められる。
5. **測定の設計への突っ込み。** 「38 問で何が測れて何が測れていないか」
   「6/20 は運用上どういう意味か」。数字の解釈は GDP の担当。

## 5. 数字を自分で再現する

```bash
pip install -e ".[dev]"
python -m pytest                                  # 約 37 分
python scripts/verify_gate_recall.py
python scripts/check_answerable_regression.py \
  tukemen-rgb/sidra-ai=. tukemen-rgb/site=<path> tukemen-rgb/creater-yard=<path> \
  tukemen-rgb/Fg=<path> tukemen-rgb/marketing=<path>       # 5 本の checkout が要る
python scripts/product_metrics.py                 # 約 5 分。--compare で前進判定
```

e5 構成は `SIDRA_EMBEDDING_MODEL_PATH`（multilingual-e5-small の重み）と
`SIDRA_EMBEDDING_QUERY_PREFIX='query: '` / `SIDRA_EMBEDDING_PASSAGE_PREFIX='passage: '`
を付けて同じコマンド。**shallow clone で測らない**——過去コミットを git に訊く
指標が 0 と読む（2026-09-16 に実際に起きた）。

## 6. やらないこと

- 秘密・トークン・個人情報を Issue・PR・プロンプト・コードに書かない。
- 質問集を増やしただけで「改善」と呼ばない（分母が変わった数字を旧数字と比べない）。
- 索引対象（`docs/`）に質問文や答えの marker を書かない。
- `docs/LANES.md` の運用（レーン分岐・Draft PR）を復活させない。
- 他 AI の成果物を理由なく消さない。差し替えるときは理由を残す。

## 7. ChatGPT に貼る文（起動プロンプト）

社長がそのまま ChatGPT に貼る想定。GitHub 連携済みなら 1 段落目だけで足りる。

```
あなたは SIDRA AI（https://github.com/tukemen-rgb/sidra-ai、公開）の「GDP」役です。
役割は Issue #372「AI Review Board」本文のとおり、戦略・製品観点のレビュー、優先順位への異議、
数字の解釈です。実装は Claude の自動ループが行います。

最初に docs/HANDOFF_GDP.md を読み、そこに書かれた順で README.md → docs/COLLABORATION.md →
docs/SECURITY.md → docs/OUTCOMES.md → docs/BACKLOG.md（先頭〜完了条件と E 節）→
docs/LOOP_LOG.md の末尾 → Issue #372 の全コメントを読んでください。

守ること: 1 コメント 1 論点。提案には動かしたい数字（例: answerable paraphrase 6/20）を
必ず書く。事実は docs/OUTCOMES.md と実測を正とし、推測で数字を書かない。不変条件
（GitHub read-only／外部 LLM API 不使用／loopback 既定／秘密を書かない／本番 deploy しない／
GAMEYARD・CreatorYard 本体を変えない）に触れる提案は「要判断」と明記する。
API キー・トークン・パスワード・個人情報は絶対に書かない。

最初の成果物: HANDOFF_GDP.md §4 の 5 論点のうち、あなたが最も数字を動かせると考える
1 つを選び、Issue #372 に投稿できる形（論点・動かしたい数字・根拠・検証手順）で
コメント案を 1 本書いてください。投稿は私（社長）が行います。
```
