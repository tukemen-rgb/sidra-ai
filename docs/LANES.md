# SIDRA AI 並行開発レーン (GDP)

6本のレーンが1時間ごとに並行して走る。各レーンは**担当ファイルが重複しない**ため、
同時に走っても Git 上で衝突しない。Claude は3時間に1回、横串レビューだけを行う。

## 役割分担

| 実行者 | 頻度 | 役割 |
| --- | --- | --- |
| 各レーン (Codex / 自動化) | 1時間ごと × 6本 | 担当範囲の小さな増分実装 |
| Claude | 3時間ごと × 1本 | 横串レビュー・衝突検出・不変条件の検証 |

## ベース

- ベースブランチ: `claude/sidra-ai-gdp-qecrab` (PR #2 / SIDRA AI v0.1)
- 各レーンはここから分岐し、**main へは直接 push / merge しない**
- PR は必ず Draft

## レーン定義

| # | ブランチ | 担当ファイル（このレーンだけが編集可） | テーマ |
| --- | --- | --- | --- |
| L1 | `claude/gdp-l1-retrieval` | `src/sidra_ai/retrieval/**`<br>`tests/test_store_and_retrieval.py` | 検索品質・永続化 |
| L2 | `claude/gdp-l2-security` | `src/sidra_ai/security/**`<br>`tests/test_security_gate.py`<br>`tests/test_data_not_instructions.py` | 検知精度・出力側走査 |
| L3 | `claude/gdp-l3-ingestion` | `src/sidra_ai/ingestion/**`<br>`tests/test_ingestion_diff.py` | 差分取得の堅牢化 |
| L4 | `claude/gdp-l4-models` | `src/sidra_ai/models/**`<br>`tests/test_config_and_models.py` | ローカル32B化の道筋 |
| L5 | `claude/gdp-l5-api` | `src/sidra_ai/api/**`<br>`tests/test_api.py` | API 堅牢化・監査 |
| L6 | `claude/gdp-l6-evals` | `src/sidra_ai/evals/**`<br>`docs/**`<br>`tests/test_evals.py` | 評価・コスト・文書 |

### 共有ファイル（全レーン編集禁止）

衝突が起きる唯一の場所なので凍結する。

- `src/sidra_ai/documents.py` — RAG スキーマ
- `src/sidra_ai/config/settings.py` — 設定
- `tests/conftest.py` — 共通 fixture
- `pyproject.toml`
- `README.md`
- `docs/LANES.md`（この文書）

**変更が必要になった場合は実装せず、PR 本文の「要調整」節に理由と差分案だけ書く。**
横串レビュー（Claude）が裁定し、ベースブランチ側で一本化する。

## 各レーンのタスク候補（優先度順）

### L1 検索品質・永続化
1. sqlite + FTS5 による索引の永続化（`DocumentStore` の外部 interface は変えない）
2. 同一ドキュメントのチャンクが上位を占める問題の抑制（document 単位の多様性確保）
3. `Retriever` を ABC 化し、将来のローカル埋め込みモデルに差し替え可能にする
4. 日本語 bigram トークナイザの精度検証と回帰テスト
5. BM25 パラメータ (k1, b) の調整とベンチ

### L2 検知精度・出力側走査
1. 検知前に Unicode NFKC 正規化を適用し、全角・異体字による回避を潰す
2. prompt injection コーパスの拡充（多言語、エンコード回避、分割記述）
3. モデル出力側の secret スキャン（返す前に走査し、漏れていれば差し止め）
4. secret 検知の false positive 実測と閾値調整（ノイズ化すると無視されるため最優先級）
5. quarantine の release ワークフロー（CLI、人間承認前提）

### L3 差分取得の堅牢化
1. `compare` API の打ち切り検知（250 commits / 300 files）→ full re-ingest フォールバック
2. Link header によるページネーション対応
3. ETag / `If-None-Match` による API 節約
4. `X-RateLimit-Remaining` の尊重とバックオフ
5. PR / Issue のコメントスレッド取り込み（trust は `EXTERNAL`）

### L4 ローカル32B化の道筋
1. ベンチハーネス（トークン/秒、メモリ、量子化別）
2. streaming 生成を interface に追加（`generate_stream`）
3. context window 超過時のチャンク削減とトークン予算管理
4. backend health check の強化とフォールバック順序
5. batching / KV cache の抽象化

### L5 API 堅牢化・監査
1. 監査ログ（クエリ、判定、引用元。秘密値は残さない）
2. `POST /v1/retrieve` — 引用のみ返し LLM を使わない = 外部コスト 0 円の経路
3. quarantine release エンドポイント（人間承認フロー）
4. structured logging と request id
5. 認証の強化（token rotation、失敗回数制限）

### L6 評価・コスト・文書
1. eval ケース拡充（多言語 injection、provenance 欠落、差分取得の異常系）
2. 外部 API 0 円の継続検証（依存グラフ走査テストの強化）
3. トークン/コスト計測レポート
4. `docs/SECURITY.md` の既知ギャップの解消状況を更新
5. ADR（設計判断記録）の導入

## 全レーン共通の厳守事項

1. **1回の起動で1テーマ、目安 400 行以内**。超える場合は分割し、残りを PR 本文に書く。
2. `pytest` 全 green が必須。落ちたら直すか変更を revert する。
3. API key / token / password / 個人情報 を、コード・commit・ログ・テストデータに書かない。
   認証情報の形をしたテスト値は必ず反復で生成する（例: `"ghp_" + "0" * 36`）。
4. 外部 LLM API を使わない。有料 API を依存に追加しない。
5. GitHub への**書き込み機能を実装しない**（v0.1 は read-only）。
6. 本番 deploy をしない。GAMEYARD / CreatorYard 本体を変更しない。
7. 他 AI の成果物を理由なく削除しない。
8. 変更が不要なら何もせず no-op で終える。**空回しのコミットを作らない。**

## 横串レビュー（Claude、3時間ごと）

各回で確認する:

1. **衝突** — 共有ファイルへの侵入、レーン間の担当違反、重複実装
2. **不変条件** — 全レーンのブランチで以下が壊れていないこと
   - GitHub write 操作が存在しない
   - 取得コンテンツが DATA 扱いのまま（命令に昇格していない）
   - secret / PII が索引に入らない
   - localhost がデフォルト
   - 外部有料 API に依存していない
3. **乖離** — ベースブランチからの drift、rebase の要否
4. **要調整** — 各 PR に上がった共有ファイル変更要求の裁定
5. **報告** — 結果を PR #2 にコメント。異常があれば該当レーンの PR にも記載

裁定の原則は `docs/COLLABORATION.md` に従う。
「どの AI が書いたか」ではなく、ユーザー価値・収益・実現性・差別化・セキュリティ・
保守性で最も高い実装を採る。
