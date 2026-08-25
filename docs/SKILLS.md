# 導入済み Claude Skills

2026-08-25、社長指示「さまざまな Claude の skills を沢山インプット（安全な
オープンソース）してアウトプット出来るようにして」により導入。

出所は Anthropic 公式の公開リポジトリ **github.com/anthropics/skills**
（改変なしでコピー。各 skill ディレクトリの `LICENSE.txt` が原文のまま
入っている。ライセンスは OSI オープンソースではなく「Anthropic のサービス
利用契約の下での利用」——つまり **Claude のセッションで使うことがそのまま
許諾範囲**。第三者への再配布や他社 AI での利用はしない）。

## 使い方

このリポジトリを clone したセッション（毎時ループ・クラウドセッション・
社長の手元の Claude Code）で自動的に読み込まれる。`/docx` のように
スラッシュコマンドで呼ぶか、該当作業を頼めば Claude が自動で使う。

## 導入した 15 skills

| skill | 何がアウトプットできるか |
|---|---|
| `docx` | Word 文書（企画書・レター・トラック変更つき文書） |
| `pptx` | PowerPoint（ピッチ資料・スポンサー営業デッキ） |
| `xlsx` | Excel（受注台帳・KPI シート・数式つき集計） |
| `pdf` | PDF の生成・結合・分割・フォーム記入 |
| `frontend-design` | 見栄えのする Web UI/フロントエンド実装 |
| `web-artifacts-builder` | リッチな単一ファイル Web アプリ/Artifact |
| `theme-factory` | Artifact/資料へのテーマ（配色・タイポ）適用 |
| `algorithmic-art` | p5.js 等によるジェネラティブアート（GAMEYARD ビジュアル素材） |
| `slack-gif-creator` | アニメ GIF 生成（SNS 運用の素材にも使える） |
| `webapp-testing` | Playwright での Web アプリ実機テスト |
| `mcp-builder` | MCP サーバーの設計・実装 |
| `skill-creator` | 新しい skill を自作するための skill |
| `doc-coauthoring` | 文書の共同執筆ワークフロー |
| `internal-comms` | 社内向け文書・アナウンスの書き方 |
| `discernment-nudge` | 回答の検証を促す確認質問を付ける（本プロジェクトの実測文化と相性が良い） |

## 追加分（2026-08-25 第2弾、社長指示「もっとコピーして」）

**obra/superpowers**（github.com/obra/superpowers、**MIT ライセンス** =
完全なオープンソース。各ディレクトリに LICENSE を同梱）から開発プロセス系
14 skills。ループ自身の作業品質にも効く:

| skill | 中身 |
|---|---|
| `systematic-debugging` | 症状いじりでなく根本原因を先に特定する手順 |
| `test-driven-development` | RED→GREEN→REFACTOR の徹底 |
| `verification-before-completion` | 「完了」を名乗る前の検証手順 |
| `writing-plans` / `executing-plans` | 実装計画の書き方と実行 |
| `brainstorming` | 設計前の発散→収束 |
| `requesting-code-review` / `receiving-code-review` | レビュー依頼と受け方 |
| `subagent-driven-development` / `dispatching-parallel-agents` | サブエージェント分業 |
| `using-git-worktrees` / `finishing-a-development-branch` | ブランチ運用 |
| `writing-skills` / `using-superpowers` | skill 自作と使い分け |

**anthropics/skills** から前回見送った `canvas-design`（ポスター・バナー等の
ビジュアルカンバス制作。同梱フォント 5.5MB 込み）も追加した。clone が
その分重くなるコストは社長指示（もっと）を優先して受け入れた。

## 追加分（2026-08-25 第3弾、社長指示「百個ぐらいをコピーしたい」）— 計 98 個

skills.sh レジストリ上位から、**組織として実在し・ライセンスが明確（全て MIT）**な
コレクションのみ選定。全スクリプトを外部通信スキャンした上で導入:

| ソース | 数 | 中身 |
|---|---|---|
| vercel-labs/agent-skills (MIT, README 宣言) | 7 | react-best-practices / web-design-guidelines / composition-patterns / react-view-transitions / react-native-skills / writing-guidelines / vercel-optimize — **GAMEYARD(Next.js) の UI 実装にそのまま効く** |
| mattpocock/skills (MIT) | 32 | tdd / diagnosing-bugs / domain-modeling / codebase-design / to-spec / to-tickets / triage / handoff / teach ほか（in-progress 印の 8 個含む） |
| expo/skills (MIT) | 18 | Expo/React Native 全般 — 将来のモバイル展開用 |
| prisma/skills (MIT) | 9 | Prisma ORM / Postgres セットアップ |
| supabase/agent-skills (MIT) | 2 | supabase / postgres ベストプラクティス |

**除外したもの（理由つき）**: vercel の `deploy-to-vercel` と
`vercel-cli-with-tokens`（スクリプトが外部へアップロードする実通信あり、かつ
本プロジェクトの「本番 deploy をしない」方針に抵触）、expo の `eas-*` 6 個と
`expo-skill-eval` / `expo-skill-feedback`（EAS サービス通信・作者内部用）、
mattpocock の `ask-matt` / `setup-matt-pocock-skills` / `migrate-to-shoehorn` /
`scaffold-exercises`（作者個人・私物ライブラリ用）、同 `code-review`
（Claude Code 組み込みの /code-review と名前衝突）。

## 導入時の安全レビュー（2026-08-25 実施）

- 全 skill のスクリプト（`*.py` / `*.sh`）を走査し、**実行時に外部へ通信する
  コードが無い**ことを確認した（唯一のヒットは `mcp-builder/reference/` の
  ドキュメント内サンプルコードで、実行されない）。
- 公式リポジトリからの**改変なしコピー**。更新するときは同リポジトリから
  取り直し、このレビューをやり直すこと。
- 導入を見送ったもの: `canvas-design`（同梱フォント 5.5MB で clone が
  毎時重くなる）、`claude-api`（本プロジェクトは外部 LLM API を使わない方針の
  ため誤用の芽を作らない）、`brand-guidelines` / `academy-guide`
  （Anthropic 社内向けで本プロジェクトに関係がない）。必要になれば
  同じ手順で追加できる。

## ループへの注意

- skill は**道具**であり、キューの完了条件（数字が動いたか）を変えない。
- skill のスクリプトが要求する pip パッケージ（python-docx / python-pptx /
  openpyxl / pypdf 等）は使うときにインストールする。製品
  （`pyproject.toml`）の依存には**足さない**。
