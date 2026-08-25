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
