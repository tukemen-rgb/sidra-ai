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

The codebase now includes a strict local model manifest and an observed-NVIDIA-
VRAM routing path for reviewed non-echo models. **That path is not yet mandatory
inside `SidraService` startup.** Until Issue #89 is closed, the verified API
startup baseline remains `echo`; treat Ollama/llama.cpp setup as staging and
routing-validation work rather than as a completed fail-closed runtime path.

Run `python -m sidra_ai.local_preflight` before starting a home-PC runtime. See
`docs/LOCAL_RUNTIME.md` for the safe install, hardware observation, local model
artifact, and acceptance procedure. See `docs/ARCHITECTURE.md` for the module map
and `docs/SECURITY.md` for the threat model and known gaps.

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
5. local model adapters and constrained-hardware routing components
6. security gate and output guard
7. offline evaluation suite
8. private SIDRA API (`/health`, `/v1/retrieve`, `/v1/chat`, `/v1/github/analyze`)

The remaining local-model integration gap is tracked in Issue #89: non-echo
`SidraService` startup must be forced through reviewed manifest metadata and a
fresh observed-VRAM admission decision before the real-model runtime is treated
as fully integrated.

See `docs/COLLABORATION.md` for the shared implementation protocol.
