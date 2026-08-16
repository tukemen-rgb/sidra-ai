# SIDRA AI local runtime setup

This guide prepares a home/owned PC for the verified SIDRA AI v0.1 runtime.
It is an installation and verification procedure, **not** evidence that any
particular PC has already been configured.

## Safety baseline

Keep these invariants throughout setup and normal operation:

- run SIDRA AI in a dedicated Python virtual environment;
- keep the SIDRA API on `127.0.0.1` for the home-PC baseline;
- use only the registered v0.1 model backends: `echo`, `ollama`, `llama_cpp`;
- keep Ollama / llama.cpp inference endpoints on loopback;
- pre-stage model artifacts during an explicit install/staging step; do not add
  an external-LLM fallback to the Core runtime;
- never commit API tokens, GitHub tokens, model files, quarantine data, or
  production/private data;
- treat `.sidra/` as sensitive local state because it can contain indexed or
  quarantined content;
- do not install the `transformers` extra for v0.1. That backend is deliberately
  not selectable until local-artifact-only loading is implemented and verified.

The normal runtime can work with no paid LLM API and no GitHub token.

### Current non-echo runtime status

The repository now contains a strict local model manifest parser and a verified
model-layer path that can perform:

`reviewed manifest -> observed NVIDIA free VRAM -> exact configured candidate -> admitted context cap -> adapter`

That path is **not yet mandatory inside `SidraService` startup**. The composition
root still constructs the configured model through `adapter_from_settings()`.
Issue #89 tracks the remaining L4/L5 wiring. Until that issue is closed and the
combined exact-SHA gate is green, use `echo` as the verified API-startup baseline.
You may stage Ollama/llama.cpp models and validate manifest/routing metadata, but
do not call the home PC "real-model SIDRA-ready" yet.

## 1. Install the Python environment

Requirements:

- Python 3.11 or newer;
- Git;
- optional NVIDIA driver + `nvidia-smi` for NVIDIA VRAM observation;
- either Ollama or llama.cpp only when moving beyond the default `echo` backend.

Use a dedicated environment so unrelated packages (especially external LLM
provider SDKs) cannot silently enter the SIDRA runtime graph.

### Windows PowerShell

```powershell
git clone https://github.com/tukemen-rgb/sidra-ai.git
cd sidra-ai
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### Linux / macOS

```bash
git clone https://github.com/tukemen-rgb/sidra-ai.git
cd sidra-ai
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Package download is an **installation/build activity**. Normal Core runtime
operation should not depend on package-registry access or an external LLM API.

## 2. Run the offline baseline before adding a real model

```bash
python -m pytest
sidra-evals
python -m sidra_ai.local_preflight
```

The preflight does not start a model, open a server socket, call GitHub, or make
an external network request. It validates the current environment/configuration,
checks that the dedicated venv contains no blocked external-LLM provider SDK,
constructs the configured adapter without contacting it, and optionally reads
aggregate NVIDIA VRAM counters through the fixed local `nvidia-smi` probe.

A healthy default setup should report `"ok": true`, `"api_loopback_only": true`,
`"configured_backend": "echo"`, and `"external_llm_provider_sdks": "clear"`.
`"gpu_probe": {"status": "unavailable"}` is not an error on a CPU/non-NVIDIA
machine.

If the preflight reports a blocked provider SDK, create a clean dedicated venv
rather than modifying another project's environment.

## 3. Environment configuration: important `.env` note

`.env.example` is a **template only**. SIDRA AI v0.1 does not load `.env`
automatically and does not depend on `python-dotenv`. Export/set variables in
the process environment (or use a separately reviewed local service manager).
The `.env` file name is gitignored as defense in depth, but merely copying it
does not configure the process.

Safe default examples:

### Windows PowerShell

```powershell
$env:SIDRA_HOST = "127.0.0.1"
$env:SIDRA_MODEL_BACKEND = "echo"
python -m sidra_ai.local_preflight
```

### Linux / macOS

```bash
export SIDRA_HOST=127.0.0.1
export SIDRA_MODEL_BACKEND=echo
python -m sidra_ai.local_preflight
```

Do not paste real tokens into documentation, shell scripts, Git commits, issue
comments, or command history. A GitHub token is optional for public repositories.
If private-repository access is needed, use a fine-grained **read-only** token
for the shortest practical local session.

## 4. Check local NVIDIA VRAM before choosing a model

SIDRA includes a bounded, shell-free `nvidia-smi` probe. The preflight reports
only total/free MiB and the local device index; it does not start a model.

Manual cross-check:

```bash
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits
```

The routing layer can cap admission by observed free VRAM. Do not choose a model
from parameter count alone. Record measured weight memory, KV-cache growth,
planned context, and a safety reserve; unknown memory demand should fail closed.

## 5. Pre-stage a local model artifact and routing manifest

Model acquisition belongs to an explicit staging step, separate from Core
runtime operation. Keep model artifacts outside the Git repository, for example
under an owned local directory such as `C:\SIDRA\models` or `/srv/sidra/models`.

For every model/quantization, retain a local record (not a secret) containing:

- upstream publisher/source;
- exact model identifier and immutable revision/digest where available;
- local filename or Ollama model tag;
- SHA-256 for file-based artifacts such as GGUF;
- license and redistribution/use constraints;
- quantization label;
- measured VRAM/KV-cache/context values used by routing.

Do not treat a mutable model name such as `latest` as sufficient provenance for
a promoted runtime.

SIDRA's strict local manifest parser accepts a bounded JSON document with
explicit routing metadata. A minimal reviewed record has this shape:

```json
{
  "version": 1,
  "models": [
    {
      "backend": "ollama",
      "model": "local-reviewed-tag",
      "weights_vram_mib": 1800,
      "kv_cache_mib_per_1k_tokens": 100,
      "max_context_tokens": 4096,
      "quantization": "Q4_K_M",
      "priority": 10,
      "license": "record-the-real-license",
      "revision": "immutable-local-or-upstream-revision"
    }
  ]
}
```

These numbers are examples of the schema only, **not model recommendations or
measurements**. Replace them with measured or conservative values for the exact
artifact. URL-shaped model references, unknown fields, missing KV/context data,
symlinked manifests, and missing revision/artifact provenance fail closed.

The parser/routing helpers do not automatically make this manifest part of
`SidraService` yet; Issue #89 must be completed before real-model API startup is
considered fully admission-controlled.

### llama.cpp / GGUF

Verify a pre-staged GGUF before use.

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 C:\SIDRA\models\model.gguf
```

Linux / macOS:

```bash
sha256sum /srv/sidra/models/model.gguf
```

Start the local inference server on loopback only (confirm flags against the
installed llama.cpp release):

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
```

For staging/routing validation you may prepare the corresponding environment:

```bash
export SIDRA_MODEL_BACKEND=llama_cpp
export SIDRA_MODEL_NAME=local-gguf
export SIDRA_MODEL_ENDPOINT=http://127.0.0.1:8080
python -m sidra_ai.local_preflight
```

PowerShell uses the equivalent `$env:NAME = "value"` syntax. Until Issue #89 is
closed, switch back to `SIDRA_MODEL_BACKEND=echo` for the verified API-startup
baseline.

### Ollama

Install Ollama from its official distribution, then acquire the chosen model
only during the explicit staging/install phase. Record the exact model tag and
vendor-reported digest/revision when available. Do not configure a remote Ollama
host as a SIDRA v0.1 inference endpoint.

```bash
export SIDRA_MODEL_BACKEND=ollama
export SIDRA_MODEL_NAME=<pre-staged-local-model-tag>
export SIDRA_MODEL_ENDPOINT=http://127.0.0.1:11434
python -m sidra_ai.local_preflight
```

The preflight validates endpoint locality but deliberately does **not** contact
the Ollama daemon or generate text. Until Issue #89 is closed, this is staging
and validation, not proof that normal `SidraService` startup enforced the
manifest/VRAM admission path.

## 6. Start and verify the SIDRA API

The verified API-startup baseline is currently `echo`. After offline tests,
evals, and configuration preflight are green:

```bash
export SIDRA_MODEL_BACKEND=echo
sidra-api
```

In a second terminal:

```bash
curl http://127.0.0.1:8787/health
```

PowerShell alternative:

```powershell
$env:SIDRA_MODEL_BACKEND = "echo"
Invoke-RestMethod http://127.0.0.1:8787/health
```

After Issue #89 is completed and revalidated, this section can be expanded to
make the reviewed manifest + observed-VRAM route mandatory for Ollama/llama.cpp
startup before the API socket is opened.

## 7. GitHub RAG verification

Public repositories require no token. If an optional read-only GitHub token is
configured, v0.1 pins authenticated ingestion to `https://api.github.com` and
has no GitHub write code path.

Run a known-repository analysis only after the local API is healthy:

```bash
curl -X POST http://127.0.0.1:8787/v1/github/analyze \
  -H 'content-type: application/json' \
  -d '{"repositories":["tukemen-rgb/sidra-ai"]}'
```

The retrieved material remains DATA, passes through the Security Gate, and must
retain provenance/citations.

## Acceptance criteria for an owned-PC install

Do not call the machine "SIDRA-ready" until all applicable checks are true:

1. dedicated Python 3.11+ venv is active;
2. full `pytest` is green in that checkout;
3. `sidra-evals` is green;
4. `python -m sidra_ai.local_preflight` returns `ok: true`;
5. API bind remains loopback-only;
6. selected API-startup backend is `echo` until Issue #89 is closed;
7. any staged real model artifact/tag has recorded source/revision/license and
   integrity evidence appropriate to that backend;
8. any staged real model has reviewed manifest metadata for weights VRAM,
   KV-cache growth, maximum context and quantization;
9. NVIDIA routing validation has a trustworthy local free-VRAM observation;
10. `sidra-api` starts without exposing a public socket;
11. `/health` succeeds on the verified API-startup baseline;
12. no paid/external LLM fallback is configured;
13. no production publish, GAMEYARD/CreatorYard connection, billing, external
    write/send, or destructive operation has been enabled as part of this setup.

After Issue #89 closes, add the real-model runtime acceptance checks: mandatory
manifest match, fresh VRAM probe, no static-budget fallback, admitted context
cap preserved by the adapter, and successful loopback model health.

A failure in any required check is a stop condition, not a reason to weaken the
corresponding safety gate.
