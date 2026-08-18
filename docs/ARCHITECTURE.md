# SIDRA AI v0.1 Architecture

## Shape

```text
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

The promoted v0.1 `main` baseline is the path above. The current post-v0.1
integration candidate also contains an isolated Fetch Plane library:

```text
allowlisted HTTPS URL
      |
      v
fetch/      -- static URL policy -> bounded DNS -> pinned-IP TLS GET -> manual redirect revalidation
      |
      v
WebIngestionBridge -> Provenance(SourceType.WEB, EXTERNAL) -> Web-scoped SecurityGate
      |
      v  (ALLOW only)
retrieval/
```

That Fetch Plane is not wired into `sidra-api`, has no default allowed hosts,
and has no environment-driven host allowlist. The presence of `fetch/` source
on an integration branch therefore does not mean general Web research is
runtime-enabled.

`api/service.py` is the v0.1 composition root. Everything else is a leaf that
can be tested on its own. Fetch Plane remains constructor-injected and outside
that API composition root until a separate reviewed exposure change is made.

## Module responsibilities

| Module | Responsibility | Key invariant |
| --- | --- | --- |
| `documents.py` | `Provenance`, `Document`, `Chunk`, `TrustLevel` | provenance validated on construction |
| `config/` | env-driven `Settings` | localhost default; secrets read at access time, never stored |
| `ingestion/` | GitHub read-only fetch, SHA/activity state, normalization | GET only; commit and mutable-source freshness are tracked separately |
| `fetch/` | post-v0.1 bounded Web Fetch Plane | exact-host HTTPS GET only; zero hosts by default; DNS/IP + redirect fail closed; pinned destination IP; no API wiring |
| `security/` | detectors, gate, redaction, DATA envelope | decide + record; never silently delete |
| `retrieval/` | chunking, index, BM25 search | only `ALLOW` content is indexable |
| `models/` | replaceable local backends | only verified local backends can be selected; no paid API can be registered |
| `evals/` | offline security/grounding regression suite | runs with no network and no model weights |
| `api/` | private HTTP surface | four routes; no write/deploy/Web-fetch route exists |

## Post-v0.1 Fetch Plane boundary

The current integration candidate implements the approved read-only Fetch Plane
as a separate capability rather than a generic outbound HTTP client for Core or
models.

Current invariants are:

- `FetchPolicy()` defaults to an empty exact-host allowlist;
- only `https` on port 443 is accepted;
- userinfo, fragments, IP-literal targets, non-ASCII hostname input and query
  strings are rejected before DNS;
- every supplied A/AAAA answer must be globally routable; mixed safe/unsafe
  answer sets fail closed rather than filtering the unsafe address;
- `PinnedHttpsTransport` connects to the exact validated IP and preserves the
  original allowlisted hostname for TLS SNI, certificate verification and the
  HTTP `Host` header;
- the transport exposes only GET and has no proxy, cookie jar, ambient
  Authorization, `.netrc`, client-certificate, request-body or automatic
  redirect capability;
- redirects are followed only by `FetchBroker`, with static URL policy, fresh
  DNS/IP validation, canonicalization and loop/count checks repeated before the
  next transport call;
- response status/content type/body size and connect/read/overall time are
  bounded; only `text/plain`, `text/html`, and `application/json` are accepted by
  the default policy;
- `WebIngestionBridge` records canonical URL/host/retrieval time/content type,
  content digest and connected IP in provenance, marks fetched material
  `SourceType.WEB` / `TrustLevel.EXTERNAL`, runs a capability-scoped Security
  Gate, and indexes only `ALLOW` output;
- no paid/external LLM fallback, browser session, authenticated Web session,
  write/send capability, or broad default Web allowlist is introduced.

These are library-level candidate guarantees, not a statement that Web fetching
is enabled on `main` or on any home PC. Any future API/settings wiring changes
the exposure boundary and requires separate review and exact-SHA validation.

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
| Fetch Plane Web responses | `EXTERNAL` | remote content is untrusted DATA even when its host is allowlisted |

All three are DATA. None can instruct the model.

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

For normal non-echo API startup the composition path is now:

`reviewed manifest -> exact configured model match -> fresh observed NVIDIA free VRAM -> route decision -> admitted context cap -> adapter -> API bind`

The reviewed manifest is loaded from `<SIDRA_DATA_DIR>/model-manifest.json`.
The configured backend/model must match exactly one manifest entry. The
manifest's reviewed maximum context is the v0.1 admission plan, and that same
cap is carried into the runtime adapter. Missing/invalid manifest data, probe
failure, unknown resource requirements, non-loopback model endpoint, or no
fitting route fails closed before socket bind/model use. A failed probe never
falls back to a static 6 GiB assumption, and routing never silently substitutes
a different manifest candidate.

`echo` remains the dependency-free/no-GPU baseline and bypasses GPU admission by
design. Ollama/llama.cpp normal `SidraService` construction cannot bypass the
reviewed-manifest/observed-VRAM path; explicit model injection remains only for
tests/embedding callers and is not used by the `sidra-api` entry point.

## API surface

- `GET /health` — minimal unauthenticated health status, no repository/content details.
- `POST /v1/retrieve` — authenticated/rate-limited retrieval without invoking the model.
- `POST /v1/chat` — authenticated/rate-limited grounded local-model chat.
- `POST /v1/github/analyze` — authenticated/rate-limited read-only GitHub ingestion + analysis.

No Web-fetch, write, deploy, billing, external-send, or mutation route exists.

## What is deliberately not here

- No GitHub write path, deploy, outbound message/send capability, or billing.
- No paid/external LLM fallback.
- No embeddings/vector database requirement.
- No general Web/external research route in the verified v0.1 `main` runtime.
  The post-v0.1 integration candidate contains only the isolated, default-deny
  Fetch Plane library described above; it is not API-wired or environment-
  enabled and does not authorize arbitrary crawling/search.
- No multi-node support: the rate limiter and index are in-process.
