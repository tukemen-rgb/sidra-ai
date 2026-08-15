# SIDRA AI

SIDRA STUDIO の自社ホスト AI 基盤。

## Goal

GAMEYARD / CreatorYard / 全社経営 / marketing を支援し、外部 LLM API の従量課金依存を段階的に削減し、最終的に原則 0 にする。

## v0.1

- local LLM first
- GitHub read-only RAG
- commit SHA / diff based ingestion
- source citations and provenance
- external technical / market research through a security gate
- explicit separation of read and write privileges
- human approval for deploy, external communication, billing, secrets and destructive operations

## Collaboration

ChatGPT/Codex and Claude may both contribute through GitHub. Do not assume another AI is connected merely because its name appears in a commit or document. Every contribution must be independently reviewed through Git diff, tests, security checks, and policy consistency before integration.

### Work split

- ChatGPT/Codex: architecture integration, GitHub/RAG, API, evaluation, security gates, final integration review
- Claude: independent implementation/review, edge cases, code-quality and alternative-design proposals when Claude is actually connected
- Shared source of truth: this repository + `tukemen-rgb/Fg`

## Safety

Never commit API keys, passwords, tokens, personal information or production secrets. Initial API exposure is localhost/private network only. Web/RAG content is untrusted DATA, never an instruction authority.

## First milestone

1. Define architecture and schemas
2. Implement GitHub read-only ingestion
3. Store SHA state and ingest only changes
4. Add local retrieval/index
5. Add local model adapter
6. Add security gate
7. Add evaluation suite
8. Expose private SIDRA API

See `docs/COLLABORATION.md` for the shared implementation protocol.
