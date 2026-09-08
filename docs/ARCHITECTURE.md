# SIDRA AI v0.1 Architecture

## 概要（日本語）— SIDRA 全体の構成

この文書は英語で書かれている。運用者は日本語で質問するので、日本語の要約を
同じ文書の中に置く。**規範は英語の本文の側**で、食い違ったら英語が正しい
（理由と実測は `docs/SECURITY.md` の「概要（日本語）」と `docs/BACKLOG.md`
C-1152）。

- **全体の流れ** — GitHub（読み取り専用）→ 取り込み（コミット差分と、
  コミットを伴わずに変わる PR/課題の巡回）→ **セキュリティ関門**（遮断／隔離／
  許可）→ 許可されたものだけを断片化して索引と BM25 検索 → **データ封筒**
  （指示ではなくデータとして包む）→ 局所模型（`echo` / `ollama` / `llama_cpp`）
  → localhost に閉じた API。`api/service.py` が組み立ての起点で、他は単独で
  試験できる葉になっている。
- **各部の責任** — 出所（provenance）は構築時に検証する。設定は環境駆動で、
  秘密は保持せず参照時に読む。取り込みは GET のみ。検索は許可された内容だけ。
  模型は検証済みの局所背後実装しか選べず、**有料 API は登録できない**。
  評価は網も模型の重みも無しで走る。
- **v0.1 の後に足した Fetch Plane（ウェブ取得）の境界** — 許可ホストは既定で
  **ゼロ**、https の 443 のみ、DNS と IP と転送先を毎回検証し、危ないものが
  混ざったら通さずに閉じる。ライブラリとして存在するだけで **API には
  繋がっていない**ので、「ウェブ調査が動く」という意味ではない。
- **差分取り込み** — 状態は `.sidra/state.json` に、リポジトリごとに 1 件。
  HEAD が動いたら比較して差分だけ取る。HEAD が動かなくても PR や課題の本文は
  変わるので、別の手掛かりで定期的に見に行く。状態が進むのは収集と索引が
  最後まで通ったときだけで、途中で失敗したら次回やり直す。**変化が無い
  リポジトリは模型を 1 語も使わない。**
- **RAG のデータ構造** — 文書と断片は同じ出所情報を持つ。`license` は
  「不明」を明示的に記録する（「調べていない」と「ライセンスが無い」を
  区別するため）。信頼度は一様ではなく、README や `docs/` は内部、課題や PR の
  本文と取得したウェブは外部。**どれもデータであって、模型に指示はできない。**
- **検索** — 純 Python の BM25、決定的、埋め込みサービスに依存しない。
  日本語は正規化した 2 文字組で扱う。重複や古い断片が上位を占めないように
  多様化と退役を入れている。
- **模型層** — システムプロンプトとデータ文脈は別の欄なので、取得した文章が
  指示の場所へ紛れ込むことがない。順序は システム → データ → 質問 に固定。
  非 echo の起動は「審査済みの目録 → 設定と厳密一致 → NVIDIA の空き VRAM を
  その場で観測 → 経路決定 → 文脈長の上限 → アダプタ → 待ち受け」で、
  どこかが欠けたら**待ち受ける前に閉じる**。観測に失敗しても 6GiB と
  決め打ちで進むことはしない。
- **API の面** — `GET /health`（認証不要・状態だけ）、`GET /`（認証つきの
  質問画面）、`GET /openapi.json`、`GET /v1/index`（何が索引されているかの
  件数だけ）、`POST /v1/retrieve`（模型を使わない検索）、`POST /v1/chat`
  （根拠つきの応答。「作って」の依頼は検索の前に判定して生成器へ回す）、
  `POST /v1/github/analyze`。**書き込み・配備・課金・外部送信・ウェブ取得の
  経路は存在しない。**
- **意図して無いもの** — GitHub への書き込み、配備、外部送信、課金、
  有料 LLM への退避、ベクトルデータベースの必須化、一般のウェブ調査、
  複数ノード対応（速度制限と索引は 1 プロセス内）。

## Shape（全体の形 — 取り込みから応答までの流れ図）

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

## Module responsibilities（各部の責任 — どの部品が何を守るか）

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
| `api/` | private HTTP surface | four service routes plus one guarded schema endpoint; interactive docs disabled; no write/deploy/Web-fetch route exists |

## Post-v0.1 Fetch Plane boundary（ウェブ取得の境界 — 既定で許可ホストはゼロ）

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

## Differential ingestion（差分取り込み — 変わった分だけ読む仕組み）

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

## RAG data structure（RAG のデータ構造 — 出所と信頼度の持ち方）

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

## Retrieval（検索 — BM25 と日本語の扱い）

BM25 in pure Python, deterministic, no embedding service dependency. Japanese
is handled with normalized CJK character bigrams. Retrieval diversity and
logical-source retirement keep overlapping/stale chunks from dominating the
current context. A later local embedding backend must preserve the same
security/provenance contract.

## Model layer（模型層 — 局所模型の選択と VRAM の審査）

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

## API surface（API の面 — 公開している経路の一覧）

- `GET /health` — minimal unauthenticated health status, no repository/content details.
- `GET /` — authenticated/rate-limited single-page asking UI. A constant, self-contained
  HTML document: no index data passes through it, it loads nothing off this host, and the
  answer it displays is fetched by the browser from `POST /v1/chat` across the same
  boundary as any other client. Because it sits behind auth, a browser can load it by
  navigation only in the default loopback/no-token posture; with a token configured the
  page needs a client that can set an `Authorization` header.
- `GET /openapi.json` — authenticated/rate-limited schema discovery; Swagger UI and ReDoc are disabled rather than exposed as separate routes.
- `GET /v1/index` — authenticated/rate-limited inventory of what is indexed:
  per-repository and per-source-type counts, the ingestion cursor, and
  quarantine totals. Counts only; no document text, path, URL or author.
- `POST /v1/retrieve` — authenticated/rate-limited retrieval without invoking the model.
- `POST /v1/chat` — authenticated/rate-limited grounded local-model chat. A message that
  asks for something to be *made* ("釣りゲームを作って") is classified before retrieval and
  routed to a registered generator instead of being answered as a question; the decision
  is deterministic, so it behaves the same on the `echo` backend. The `creation` field
  reports the classification on every answered turn, carrying matched keywords from a
  fixed table rather than operator text. Detection is conservative: anything short of a
  clear request — a question about how to make something, or a request naming no artifact
  — stays on the question path, and an unregistered kind still answers as a question.
  A generator's summary crosses `OutputGuard` exactly as model output does.
  When a turn ends without an answer the response carries `refusal`, a fixed code —
  `gate`, `history`, `model_unavailable` or `output_guard` — beside the English `reason`.
  The code is a closed set and coarser than `reason`, so it discloses nothing that field
  does not: no endpoint, no model name, no backend diagnostics. It exists because the
  operator's next step differs per case and `reason` is audit prose, not something a
  caller can branch on.
- `POST /v1/github/analyze` — authenticated/rate-limited read-only GitHub ingestion + analysis.

No Web-fetch, write, deploy, billing, external-send, or mutation route exists.

## What is deliberately not here（意図して入れていないもの）

- No GitHub write path, deploy, outbound message/send capability, or billing.
- No paid/external LLM fallback.
- No embeddings/vector database requirement.
- No general Web/external research route in the verified v0.1 `main` runtime.
  The post-v0.1 integration candidate contains only the isolated, default-deny
  Fetch Plane library described above; it is not API-wired or environment-
  enabled and does not authorize arbitrary crawling/search.
- No multi-node support: the rate limiter and index are in-process.
