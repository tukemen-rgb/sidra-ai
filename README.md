# SIDRA AI

SIDRA STUDIO の自社ホスト AI 基盤。

## Goal

GAMEYARD / CreatorYard / 全社経営 / marketing を支援し、外部 LLM API の従量課金依存を段階的に削減し、最終的に原則 0 にする。

## v0.1

- local LLM first
- GitHub read-only RAG
- commit SHA / diff based ingestion plus independent PR/Issue freshness polling
- source citations and provenance
- explicit separation of read and write privileges
- human approval for deploy, external communication, billing, secrets and destructive operations

The verified v0.1 runtime does **not** yet include general Web/external research ingestion. A security-gated, GET-only FetchBroker/Fetch Plane is the approved next phase and must remain separate from the local model/Core runtime.

## Getting started

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

## Collaboration

ChatGPT/Codex and Claude may both contribute through GitHub. Do not assume another AI is connected merely because its name appears in a commit or document. Every contribution must be independently reviewed through Git diff, tests, security checks, and policy consistency before integration.

### Work split

- ChatGPT/Codex: architecture integration, GitHub/RAG, API, evaluation, security gates, final integration review
- Claude: independent implementation/review, edge cases, code-quality and alternative-design proposals when Claude is actually connected
- Shared source of truth: this repository + `tukemen-rgb/Fg`

## Safety

Never commit API keys, passwords, tokens, personal information or production secrets. Initial API exposure is localhost/private network only. Retrieved GitHub data, and future Web/RAG content, are untrusted DATA, never an instruction authority.

## v0.1 baseline

The verified v0.1 baseline includes:

1. architecture and provenance schemas
2. GitHub read-only ingestion with commit and mutable-source freshness handling
3. persisted SHA/activity state with fail-closed recovery behavior
4. local retrieval/index and citations
5. local model adapters and manifest/observed-VRAM admission for configured non-echo startup
6. security gate and output guard
7. offline evaluation suite
8. private SIDRA API (`/health`, `/v1/retrieve`, `/v1/chat`, `/v1/github/analyze`)

Real-model readiness remains machine-specific: the exact local artifact/tag,
license/revision/digest evidence, manifest resource values, current free VRAM,
loopback inference endpoint and local health must all be verified on the owned
PC. No external LLM fallback is part of that runtime.

See `docs/COLLABORATION.md` for the shared implementation protocol.
