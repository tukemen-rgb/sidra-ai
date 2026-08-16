# SIDRA AI v0.1 Architecture

## Shape

```
GitHub (read-only)
      |
      v
ingestion/  -- commit SHA diff + mutable PR/Issue polling --> normalize --> Document(+Provenance)
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
models/     -- LocalModelAdapter (echo | ollama | llama_cpp)
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
| `ingestion/` | GitHub read-only fetch, SHA/activity state, normalization | GET only; commit and mutable-source freshness are tracked separately |
| `security/` | detectors, gate, redaction, DATA envelope | decide + record; never silently delete |
| `retrieval/` | chunking, index, BM25 search | only `ALLOW` content is indexable |
| `models/` | replaceable local backends | only verified local backends can be selected; no paid API can be registered |
| `evals/` | offline security/grounding regression suite | runs with no network and no model weights |
| `api/` | private HTTP surface | four routes; no write/deploy route exists |

## Differential ingestion

State lives in `.sidra/state.json`, one record per repository. It tracks the
last successfully ingested commit SHA plus a local completion timestamp used
to schedule mutable PR/Issue polling.

Each run:

1. Resolve repository metadata and HEAD using read-only GitHub GET requests.
2. If HEAD changed, use `compare(base, head)` to fetch commit/file deltas.
   README and `docs/` are refreshed when touched; when compare completeness
   cannot be proven, documentation is conservatively refreshed instead of
   advancing stale knowledge.
3. If HEAD did **not** change, do not assume the repository is fully fresh.
   PR and Issue bodies/state are mutable without commits, so SIDRA periodically
   polls those sources independently using an overlapping activity cursor.
   Duplicate/materially unchanged revisions do not trigger model inference.
4. If persisted SHA state survived a process restart but the in-memory index
   did not, rebuild a safe snapshot before resuming incremental behavior.
5. Screen every candidate document through the Security Gate. Only `ALLOW`
   content is indexed; unsafe newest mutable revisions retire older safe
   revisions rather than silently serving stale content as current.
6. State advances only after a complete collection/indexing pass. Partial
   fetches fail closed and preserve the previous cursor so the next run retries.

An idle repository therefore uses bounded read-only freshness checks and zero
model tokens unless material source content changed.

## RAG data structure

Every `Document` and every `Chunk` carries the same `Provenance`:

`content`, `source`, `repository`, `path`, `commit_sha`, `timestamp`,
`source_type`, `trust_level`, `license`, plus `url`, `author`, `retrieved_at`.

Required provenance is validated on construction. `license` records
`"unknown"` explicitly rather than being omitted, so "we never checked" is
distinguishable from "there is no license".

Trust is not uniform across a repository:

| Source | Trust level | Why |
| --- | --- | --- |
| README, `docs/`, commits | `INTERNAL_REPO` | authored inside SIDRA STUDIO |
| Issues, PR bodies | `EXTERNAL` | mutable/untrusted author-controlled DATA |

Both are DATA. Neither can instruct the model.

## Retrieval

BM25 in pure Python, deterministic, no embedding service dependency. Japanese
is handled with normalized CJK character bigrams. Retrieval diversity and
logical-source retirement keep overlapping/stale chunks from dominating the
current context. A later local embedding backend must preserve the same
security/provenance contract.

## Model layer

`LocalModelAdapter` takes the system prompt and DATA context as separate
fields, so retrieved content cannot be concatenated into an instruction slot
by accident. `build_prompt` fixes the order: system → DATA → operator question.

The verified v0.1 registry exposes only:

- `echo` — dependency-free baseline for offline tests and clean-machine startup;
- `ollama` — local loopback HTTP backend;
- `llama_cpp` — local loopback HTTP backend.

`transformers` remains source-visible for future work but is deliberately **not
selectable** in v0.1. Its runtime path must first become local-artifact-only
(`local_files_only`, no remote code/weight download) and pass the same-SHA
integration gate before registration.

The model layer also provides context/token budgeting, streaming abstractions,
local benchmarking, and constrained-VRAM routing. Memory admission uses
explicit measurements/manifests rather than guessing from model names.

## API surface

- `GET /health` — minimal unauthenticated health status, no repository/content details.
- `POST /v1/retrieve` — authenticated/rate-limited retrieval without invoking the model.
- `POST /v1/chat` — authenticated/rate-limited grounded local-model chat.
- `POST /v1/github/analyze` — authenticated/rate-limited read-only GitHub ingestion + analysis.

No write, deploy, billing, external-send, or mutation route exists.

## What is deliberately not here

- No GitHub write path, deploy, outbound message/send capability, or billing.
- No paid/external LLM fallback.
- No embeddings/vector database requirement.
- No general Web/external research fetcher in the verified v0.1 runtime. The
  approved next phase is a dedicated GET-only FetchBroker/Fetch Plane with
  HTTPS/host allowlisting, DNS/IP and redirect revalidation, SSRF protections,
  size/timeout bounds, provenance, Security Gate screening, and DATA-only trust.
- No multi-node support: the rate limiter and index are in-process.
