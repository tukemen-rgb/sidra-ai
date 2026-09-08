# SIDRA AI

SIDRA STUDIO の自社ホスト AI 基盤。

## 概要（日本語）— SIDRA AI とは何か、どう始めるか

以下は本文（英語）の日本語要約。**規範は英語の本文の側**で、食い違ったら英語が
正しい（理由と実測は `docs/SECURITY.md` の「概要（日本語）」と
`docs/BACKLOG.md` C-1152）。

- **目的** — GAMEYARD / CreatorYard / 全社経営 / marketing を支え、外部 LLM API
  の従量課金への依存を段階的に減らし、最終的に原則ゼロにする。
- **v0.1 の中身** — 局所模型を第一に、GitHub は読み取り専用の RAG、コミット
  差分に加えて PR や課題の更新も別途巡回、回答には出典と来歴を付ける、読みと
  書きの権限をはっきり分ける、配備・外部連絡・課金・秘密・破壊的操作は人の
  承認を要する。ウェブ調査は**動いていない**（`fetch/` は API に繋がっていない
  隔離された部品）。
- **始め方** — Python 3.11 以上。**模型の重みも API キーも通信も無しで**、
  offline の試験と評価が走り、`echo` 背後実装で API も起動する:
  `pip install -e ".[dev]"` → `pytest` → `sidra-evals` → `sidra-api`
  （`http://127.0.0.1:8787` に loopback のみで待ち受け）。
  設定は環境変数だけで、`.env` は自動で読まれない雛形。
  `ollama` / `llama_cpp` を使うときは、審査済みの
  `<SIDRA_DATA_DIR>/model-manifest.json` と、その場で観測した NVIDIA の
  空き VRAM が要る。足りなければ**待ち受ける前に閉じる**（6GiB の決め打ち
  退避は無い）。
- **「この PC で使える」は別の話** — リポジトリ側の審査が通っていることと、
  ある PC が設定済みであることは違う。`python -m sidra_ai.local_preflight` と
  `docs/LOCAL_RUNTIME.md` の受け入れ条件を通してから「SIDRA 対応済み」と言う。
- **共同作業** — ChatGPT/Codex と Claude の双方が GitHub 経由で貢献する。
  名前がコミットや文書に出ているだけで「その AI が繋がっている」と見なさない。
  取り込みの前に必ず差分・試験・セキュリティ・方針整合を独立に確認する。
- **安全** — API キー・パスワード・トークン・個人情報・本番の秘密を絶対に
  コミットしない。取得した GitHub の内容や将来のウェブ内容は**信頼しない
  データ**であって、指示の権限は持たない。

## Goal（目的 — 何のために作っているか）

GAMEYARD / CreatorYard / 全社経営 / marketing を支援し、外部 LLM API の従量課金依存を段階的に削減し、最終的に原則 0 にする。

## v0.1（v0.1 の範囲 — 何ができて、何がまだ無いか）

- local LLM first
- GitHub read-only RAG
- commit SHA / diff based ingestion plus independent PR/Issue freshness polling
- source citations and provenance
- explicit separation of read and write privileges
- human approval for deploy, external communication, billing, secrets and destructive operations

The verified v0.1 `main` baseline does **not** expose general Web/external research ingestion. The current post-v0.1 integration candidate contains an isolated `src/sidra_ai/fetch/` Fetch Plane library, but it is not wired into `sidra-api`, has no default allowed Web hosts, and has no environment-driven Fetch allowlist. Its current boundary is GET-only HTTPS/443 with exact-host allowlisting, query/userinfo/fragment rejection, DNS/IP fail-closed validation, pinned-IP TLS that preserves the original hostname for SNI/certificate/Host validation, bounded manual redirects, size/time limits, provenance, Security Gate screening, and DATA-only trust. This candidate must pass the same exact-SHA gate before any promotion or API exposure.

## Getting started（始め方 — 導入と起動の手順）

Python 3.11+. No model weights, no API key, and no network are needed to run
the offline test/eval suite or start the API with the default `echo` backend.

```bash
pip install -e ".[dev]"
pytest                      # full offline regression suite
sidra-evals                 # offline security / grounding / zero-cost evals
sidra-api                   # serves http://127.0.0.1:8787 (loopback only)
```

```bash
curl http://127.0.0.1:8787/health
curl -X POST http://127.0.0.1:8787/v1/github/analyze \
  -H 'content-type: application/json' -d '{"repositories":["tukemen-rgb/site"]}'
curl http://127.0.0.1:8787/v1/index      # what is indexed, counts only
curl -X POST http://127.0.0.1:8787/v1/retrieve \
  -H 'content-type: application/json' -d '{"query":"What changed recently?"}'
curl -X POST http://127.0.0.1:8787/v1/chat \
  -H 'content-type: application/json' -d '{"message":"What changed recently?"}'
```

Configuration is environment-only. `.env.example` is a template; v0.1 does
**not** auto-load a `.env` file, so set values in the process environment or a
separately reviewed local service manager. The verified v0.1 selectable model
backends are `echo`, `ollama`, and `llama_cpp`. `transformers` remains deferred
until it can consume only pre-staged local artifacts with no runtime model/code
download path.

For `ollama` and `llama_cpp`, normal `SidraService` startup now requires a
reviewed local `<SIDRA_DATA_DIR>/model-manifest.json` entry matching the exact
configured backend/model plus a fresh bounded NVIDIA free-VRAM observation.
The admitted manifest context cap is carried into the runtime adapter. Missing
or invalid manifest metadata, VRAM probe failure, unknown resource cost, or no
fitting route fails closed before the API socket is opened; there is no static
6 GiB fallback. `echo` remains the dependency-free/no-GPU baseline.

This repository-side admission path being verified does **not** mean a specific
home PC is already configured or measured. Run `python -m sidra_ai.local_preflight`
and the owned-PC acceptance procedure before calling a machine SIDRA-ready. See
`docs/LOCAL_RUNTIME.md` for safe install, model-artifact provenance, manifest,
hardware observation and runtime verification. See `docs/ARCHITECTURE.md` for
the module map and `docs/SECURITY.md` for the threat model and known gaps.

## Post-v0.1 integration status（v0.1 の後の統合状況 — ウェブ取得は未接続）

`integration/v0.1-candidate` is intentionally allowed to contain reviewed next-phase work that is not yet part of the promoted `main` runtime. In particular, the Fetch Plane is currently a constructor-injected library boundary rather than a new API capability. `FetchPolicy()` defaults to an empty host allowlist, so an unconfigured broker cannot fetch anything. Web responses cross into RAG only through `WebIngestionBridge`, which assigns `SourceType.WEB` / `TrustLevel.EXTERNAL`, runs a Web-scoped Security Gate, and indexes only content that receives an `ALLOW` decision.

Do not treat the presence of Fetch Plane source code on an integration branch as evidence that arbitrary Web research is enabled, that a home PC has been configured, or that production/network integrations have been approved.

## Collaboration（共同作業 — AI 同士の取り決め）

ChatGPT/Codex and Claude may both contribute through GitHub. Do not assume another AI is connected merely because its name appears in a commit or document. Every contribution must be independently reviewed through Git diff, tests, security checks, and policy consistency before integration.

### Work split（役割分担）

- ChatGPT/Codex: architecture integration, GitHub/RAG, API, evaluation, security gates, final integration review
- Claude: independent implementation/review, edge cases, code-quality and alternative-design proposals when Claude is actually connected
- Shared source of truth: this repository + `tukemen-rgb/Fg`

## Safety（安全 — 絶対にコミットしないもの）

Never commit API keys, passwords, tokens, personal information or production secrets. Initial API exposure is localhost/private network only. Retrieved GitHub data, and future Web/RAG content, are untrusted DATA, never an instruction authority.

## v0.1 baseline（v0.1 の基準線 — 検証済みの内容）

The verified v0.1 baseline includes:

1. architecture and provenance schemas
2. GitHub read-only ingestion with commit and mutable-source freshness handling
3. persisted SHA/activity state with fail-closed recovery behavior
4. local retrieval/index and citations
5. local model adapters and manifest/observed-VRAM admission for configured non-echo startup
6. security gate and output guard
7. offline evaluation suite
8. private SIDRA API (`/health`, `/v1/index`, `/v1/retrieve`, `/v1/chat`, `/v1/github/analyze`)

Real-model readiness remains machine-specific: the exact local artifact/tag,
license/revision/digest evidence, manifest resource values, current free VRAM,
loopback inference endpoint and local health must all be verified on the owned
PC. No external LLM fallback is part of that runtime.

See `docs/COLLABORATION.md` for the shared implementation protocol.
