# SIDRA AI v0.1 Security Model

## Threat model

SIDRA AI reads repositories that third parties can write to. An issue body,
a PR description, or a commit message is attacker-controllable text that
arrives inside otherwise trusted infrastructure. The primary threats:

1. **Prompt injection** — content instructs the assistant to exfiltrate or to
   act (push, deploy, send).
2. **Secret propagation** — a credential committed by mistake gets copied into
   the index, the logs, or a model response.
3. **PII propagation** — the same, for personal information.
4. **Scope creep** — the assistant reads or writes something outside the
   sanctioned set of repositories.
5. **Exposure** — the private API becomes reachable from the network.

## The four invariants

### 1. GitHub access is read-only

Enforced in three independent places:

- `GitHubReadOnlyClient._request` accepts only `GET`; `ALLOWED_HTTP_METHODS`
  is `{"GET"}`.
- The default transport re-checks the method.
- `tests/test_read_only.py` parses every module's AST and fails if a write
  verb or a mutating GitHub endpoint appears anywhere in the package.

There is no token scope to misconfigure into a write, because there is no
code path that would use it.

### 2. External content is DATA, never instructions

Capability-level, not prompt-level:

- Ingested content is `INTERNAL_REPO` or `EXTERNAL` trust. Both are in
  `DATA_ONLY_TRUST_LEVELS`. `DocumentStore.add` refuses anything claiming an
  instruction-level trust.
- `build_data_context` raises `InstructionAuthorityError` if a retrieved item
  claims instruction authority, and neutralizes delimiter spoofing
  (`<|im_start|>`, `system:`, forged envelope terminators) plus zero-width
  and bidi characters.
- The system prompt is a separate adapter field; retrieved text can never be
  concatenated into it.
- Most importantly: **there is nothing to coerce.** No write tool, no deploy,
  no outbound send, no spend. Successful injection in v0.1 gets a wrong
  answer, not an action.

Prompt-level defenses are treated as advisory. The guarantee is the absent
capability.

### 3. Secrets and PII never reach the index

The gate runs three detector families over every input:

- **Secrets** — provider prefixes (GitHub, AWS, Anthropic, OpenAI-shaped,
  Slack, Google), PEM private-key blocks, JWTs, credentials in URLs,
  `key = value` assignments, and high-entropy blobs. Values that are
  environment references (`os.getenv(...)`, `${VAR}`) are deliberately not
  flagged, so the correct pattern is not punished.
- **PII** — emails (role/noreply downgraded), phone numbers, Luhn-valid card
  numbers, 12-digit national-id candidates.
- **Prompt injection** — English and Japanese phrasings, delimiter spoofs,
  hidden HTML comments, invisible characters.

Detection produces a decision **and a recorded reason**, never a silent
delete:

| Decision | Meaning |
| --- | --- |
| `ALLOW` | indexable; secret/PII spans already replaced with typed `[REDACTED:…]` placeholders |
| `QUARANTINE` | kept out of the index; only sanitized review content plus minimized audit provenance is retained in `.sidra/quarantine.jsonl` (mode 0600) |
| `BLOCK` | not indexed and not passed to the model; quarantine audit is metadata-only and does not retain the blocked body |

For allowlisted quarantined input, persisted provenance keeps only the
allowlist-bound source/repository, typed fields and timestamps. Uninspected
`path`, `commit_sha`, `license`, `url`, `author`, and `extra` values are not
stored verbatim; only lengths/counts are retained where operationally useful.
Blocked or unpermitted-source input is more restrictive still and does not
persist attacker-controlled provenance strings merely for audit convenience.

`DocumentStore.add` re-runs the secret check as defense in depth: even a
hand-forged `ALLOW` verdict cannot smuggle a credential into the index
(`test_store_rejects_a_forged_allow_verdict`).

Finding evidence never carries raw surrounding text. Persisted evidence is a
context-free redacted length marker plus detector/category/reason/offset
metadata. Redaction placeholders retain an 8-character deterministic
fingerprint only for an explicit allowlist of high-search-space secret classes;
PII and low-entropy/unknown secret classes are fingerprint-free to avoid a
stable offline-guessing oracle.

### 4. The API is private by default

- Default bind is `127.0.0.1:8787`.
- Binding elsewhere requires `SIDRA_ALLOW_PUBLIC_BIND=true` **and**
  `SIDRA_API_TOKEN`. For a non-loopback bind, the token must contain at least
  24 visible ASCII characters. This is a minimum accidental-weakness guard,
  not an entropy proof; operators should generate a random token.
  `Settings.validate` raises otherwise, and `sidra-api` exits 2 rather than
  starting.
- Bearer auth applies to all `/v1` routes whenever a token is configured;
  comparison is constant-time.
- Per-client rate limiting applies to all API routes, with a separate bounded
  budget for the unauthenticated health probe.
- CORS is not enabled.
- `/health` is unauthenticated but returns only status, version, local-model
  availability, and the constant GitHub-write-disabled flag. It does not expose
  repository names, model names/endpoints, token-presence flags, index details,
  or backend exception diagnostics.
- `/v1/retrieve`, `/v1/chat`, and `/v1/github/analyze` record metadata-only
  local audit events. Raw operator text, model output, authorization headers,
  tokens, retrieved content, and gate finding evidence are excluded from the
  audit schema.

Secrets are never fields on `Settings`: `api_token` and `github_token` are
properties read from the environment on access, so they cannot appear in a
`repr`, a log line, or a serialized config dump.

Model output is a separate disclosure boundary. `OutputGuard` screens local
model text before it can be returned by chat/analyze, including bounded checks
for reversible base64/base64url, percent, hex, HTML-entity, and code-escape
representations. Secret-like or high-confidence PII findings withhold the whole
answer; detector failures fail closed and the original blocked output is not
persisted by the guard.

## Operational rules

- No credential, token, password or personal data in code, commits, issues,
  PRs, logs or test fixtures. Every credential-shaped string in this
  repository is synthetic and built by repetition
  (`"ghp_" + "0" * 36`), never pasted whole — asserted by
  `test_eval_cases_contain_no_real_credentials`.
- `.sidra/` is gitignored: it holds quarantined content and indexed text.
- Files that may hold sensitive material (`quarantine.jsonl`, a persisted
  index) are created mode 0600.

## Known gaps in v0.1

These are real and should be closed or explicitly accepted before widening the
runtime boundary:

1. **Rate limiting is in-process.** Correct for one node; a multi-node
   deployment needs a shared counter.
2. **API audit durability is best-effort.** Audit events are local and
   metadata-only, but an audit-file `OSError` deliberately does not convert an
   otherwise safe API response into a failure. Stronger durability/alerting is
   a separate operational control.
3. **Injection detection is heuristic.** It will miss novel phrasings. This
   is why the capability-level guarantee, not the detector, is the defense.
4. **High-entropy detection false-positives** on hashes and encoded assets.
   Reported at medium severity and never quarantines on its own. Dense runs
   (more than five in one document) collapse into a single LOW finding, since
   that density means encoded data rather than a leaked credential; every span
   is still redacted. Measured: 98.9% of firings were inside `.json` files.

5. **Output screening is heuristic and bounded.** The guard covers the reviewed
   secret/PII detectors and several reversible encodings with strict work
   limits, but it is not a proof of non-disclosure. Capability minimization and
   keeping secret material out of model context remain primary controls.
6. **Quarantine review is content-blind on provenance.** The release
   workflow exists (`sidra-quarantine list / show / release`), but the audit
   boundary deliberately drops an entry's path, URL and author because those
   are attacker-controlled and never pass through the detectors. A reviewer
   therefore identifies an entry by repository, source type, findings and
   redacted content - not by filename. That is a deliberate trade, and it
   makes review harder than it looks on paper.

7. **No signature verification of GitHub responses** beyond TLS.
8. **Chunk-level trust is inherited from the document**, so a doc that quotes
   a hostile issue is trusted at document level.
9. **The index is a cache of past decisions.** `DocumentStore.load()`
   re-screens every record under current policy precisely because a document
   admitted under an older detector must not be resurrected by a restart.
   `DocumentStore.rescreen_all()` covers the running process as well,
   evicting documents that no longer pass into quarantine. What remains
   manual is *calling* it: nothing triggers a rescreen automatically when a
   detector changes, so the window between fixing a detector and applying the
   fix is now bounded by an operator rather than by a restart.
10. **The gate quarantines a portion of this repository's own source, and
   this is accepted rather than fixed.** Files describing attack patterns -
   the detectors, the envelope, their tests - legitimately contain injection
   strings and synthetic credentials, because that is what a detector's
   source code *is*. SIDRA therefore cannot retrieve its own security
   implementation. Measured 2026-08-19 at 41 of 387 documents (10.6%) with
   `scripts/measure_gate_baseline.py` - a count that includes the test file
   pinning this decision, which quarantines itself for the same reason.

   *Decided:* the gate keeps judging content only. No path, directory or
   repository is exempt, and `src/sidra_ai/security/**` is not special.
   `path` is attacker-controlled provenance - gap 6 drops it from the audit
   record for exactly that reason - so an exemption keyed on it would be a
   hole shaped like a path: any document claiming the right path gets an
   unscreened channel into the index, and paths are not unique across the
   five allowlisted repositories. "Its own source" is also not a property
   the gate can see; sidra-ai is one allowlist entry among five, and giving
   it a private trust tier would make the gate's strictness depend on which
   repository asked. The relief bought - a handful of files becoming
   searchable - does not pay for that. `tests/test_security_self_source_policy.py`
   pins the refusal.

   *What to do instead.* Read the files in the repository. Retrieval is a
   convenience here, not the system of record, and the answer to "how does
   SIDRA defend itself" is in git either way. If a specific document must be
   in the index, `sidra-quarantine release` approves it by version, with an
   operator and a reason, and the ingestion side honours it.

   *The cost of that route, measured.* A release is bound to a `doc_id` over
   repository, path, commit and content, so approval cannot carry over to
   content the reviewer never saw - that part is correct and deliberate. But
   the ingestion pipeline stamps every document with the repository HEAD, so
   an unchanged file draws a new `doc_id` whenever *any* file in the
   repository is committed. Releases therefore lapse on the next commit
   rather than on the next edit to the released file, which for this
   repository's own security source makes the route close to single-use.
   That over-expiry is tracked as its own backlog item; until it is fixed,
   the honest recommendation is the repository, not the index.
11. **False-positive rate is measured, not bounded.** The current figure is
   3.5% of documents across the five allowlisted repositories
   (`docs/GATE_FALSE_POSITIVE_BASELINE.md`), re-measurable with
   `scripts/measure_gate_baseline.py`. Nothing enforces it: a change that
   doubles it passes CI. The check is a habit, not a gate.

## Verifying these claims

Do not take the table above on trust. Two commands check the parts that can
be checked mechanically:

```bash
pytest                                  # the invariants, as tests
python scripts/verify_gate_recall.py    # detection in both directions
```

`verify_gate_recall.py` exists because reviewing a security filter by reading
its patterns does not answer the question that matters. Tightening a detector
to remove false positives can silently remove a real detection, and the diff
looks the same either way. It runs 20 things that must still be caught and 9
that must no longer be flagged; a miss in the first group exits non-zero.

This is not theoretical. A digit-count check added to reduce phone-number
false positives narrowed the international pattern's floor from eight digits
to nine, dropping a real detection. The tests passed. It was caught by a
review that ran the recall set, and only after an eight-digit case was added
to it - the check was only ever as good as its cases.

## Reporting

Do not open a public issue for a security problem in this repository. Raise
it privately with the SIDRA STUDIO operator.