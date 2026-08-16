# SIDRA AI v0.1 Architecture

## Shape

```
GitHub (read-only)
      |
      v
ingestion/  -- commit SHA diff --> normalize --> Document(+Provenance)
      |
      v
security/   -- gate: block / quarantine / allow  (+ redaction, audit)
      |
      v  (ALLOW only)
retrieval/  -- chunk --> DocumentStore --> BM25Retriever
      |
      v
security/data_envelope  -- wrap as DATA, never instructions
      |
      v
models/     -- LocalModelAdapter (echo | ollama | llama_cpp | transformers)
      |
      v
api/        -- localhost-bound FastAPI, bearer auth, rate limit
```

`api/service.py` is the composition root. Everything else is a leaf that can
be tested on its own.

## Module responsibilities

| Module | Responsibility | Key invariant |
| --- | --- | --- |
| `documents.py` | `Provenance`, `Document`, `Chunk`, `TrustLevel` | provenance validated on construction |
| `config/` | env-driven `Settings` | localhost default; secrets read at access time, never stored |
| `ingestion/` | GitHub read-only fetch, SHA state, normalization | GET only; unchanged repo short-circuits |
| `security/` | detectors, gate, redaction, DATA envelope | decide + record; never silently delete |
| `retrieval/` | chunking, index, BM25 search | only `ALLOW` content is indexable |
| `models/` | replaceable local backends | no paid API can be registered |
| `evals/` | offline security regression suite | runs with no network, no weights |
| `api/` | private HTTP surface | three routes; no write route exists |

## Differential ingestion

State lives in `.sidra/state.json`, one record per repository:

```json
{"repositories": {"tukemen-rgb/site": {"last_commit_sha": "…", "last_ingested_at": "…"}}}
```

Each run:

1. `GET /repos/{repo}` and `GET /repos/{repo}/commits/{branch}` — two calls.
2. If HEAD == `last_commit_sha` and `force` is false, **stop**. `changed=False`,
   `requires_inference=False`, and `SidraService.analyze_github` returns
   without touching the model. An idle repository costs two GETs and zero
   tokens.
3. Otherwise `GET /repos/{repo}/compare/{base}...{head}` yields the commits
   and the changed file list. README and `docs/` are refetched only when the
   diff touched them (or on the first run).
4. Issues and PRs use `last_ingested_at` as an `updated_at` cursor.
5. State is written **after** indexing, so a crash re-ingests rather than
   skipping.

## RAG data structure

Every `Document` and every `Chunk` carries the same `Provenance`:

`content`, `source`, `repository`, `path`, `commit_sha`, `timestamp`,
`source_type`, `trust_level`, `license`, plus `url`, `author`, `retrieved_at`.

The first eight are required and validated; construction fails without them.
`license` records `"unknown"` explicitly rather than being omitted, so
"we never checked" is distinguishable from "there is no license".

Trust is not uniform across a repository:

| Source | Trust level | Why |
| --- | --- | --- |
| README, `docs/`, commits | `INTERNAL_REPO` | authored inside SIDRA STUDIO |
| Issues, PR bodies | `EXTERNAL` | anyone with an account can author these |

Both are DATA. Neither can instruct the model.

## Retrieval

BM25 in pure Python, deterministic, no dependencies. Japanese is handled with
CJK character bigrams rather than a morphological analyzer. Swapping in a
local embedding model later means implementing the same `search()` signature
in `retrieval/search.py`; nothing above it changes.

## Model layer

`LocalModelAdapter` takes the system prompt and the data context as separate
fields, so retrieved content cannot be concatenated into an instruction slot
by accident. `build_prompt` is shared, fixing the order: system → DATA →
operator question.

The default `echo` backend is extractive and needs nothing installed. It
exists so the pipeline is testable and the service runs on a clean machine.
Replace it with `ollama` or `llama_cpp` when weights are available; the 32B
path is a `SIDRA_MODEL_NAME` change, not a code change.

## What is deliberately not here

- No write path to GitHub, no deploy, no external communication, no billing.
- No embeddings, no vector database.
- No web/external research ingestion (the gate is built for it; the fetcher
  is not).
- No multi-node support: the rate limiter and the index are in-process.
