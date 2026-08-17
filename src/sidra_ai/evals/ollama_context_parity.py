"""Offline release gate for routed Ollama runtime-context parity.

SIDRA's local-model router admits a candidate against observed VRAM using an
explicit planned context length.  Ollama must then allocate that same context
length at runtime; otherwise the KV-cache assumption used for admission can
diverge from the backend's actual allocation.

This suite uses only in-memory adapters and payload construction.  It does not
start Ollama, touch a GPU, open a socket, or call an external API.
"""

from __future__ import annotations

from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.models.base import GenerationRequest
from sidra_ai.models.budgeted import BudgetedLocalModelAdapter
from sidra_ai.models.http_backends import OllamaAdapter
from sidra_ai.models.routing import (
    HardwareBudget,
    LocalModelCandidate,
    route_and_create_adapter,
)
from sidra_ai.models.singleflight import SingleFlightLocalModelAdapter


def _request() -> GenerationRequest:
    return GenerationRequest(system_prompt="system", user_message="question")


def _routed_context_matches_ollama_runtime_case() -> EvalOutcome:
    failures: list[str] = []
    planned_context_tokens = 2048
    candidate = LocalModelCandidate(
        backend="ollama",
        model="synthetic-local-q4",
        weights_vram_mib=3000,
        kv_cache_mib_per_1k_tokens=100,
        max_context_tokens=4096,
        quantization="Q4",
    )
    routed = route_and_create_adapter(
        [candidate],
        hardware=HardwareBudget(
            vram_mib=6144,
            reserve_vram_mib=512,
            observed_free_vram_mib=6000,
        ),
        planned_context_tokens=planned_context_tokens,
    )

    if routed.decision.planned_context_tokens != planned_context_tokens:
        failures.append("routing decision changed the reviewed planned context")

    adapter = routed.adapter
    if not isinstance(adapter, SingleFlightLocalModelAdapter):
        failures.append("constrained route did not retain the single-flight guard")
        budgeted = None
    else:
        budgeted = adapter.inner

    if not isinstance(budgeted, BudgetedLocalModelAdapter):
        failures.append("routed adapter did not retain the context budget wrapper")
        ollama = None
    else:
        if budgeted.max_context_tokens != planned_context_tokens:
            failures.append("budget wrapper context diverged from routing admission")
        ollama = budgeted.inner

    if not isinstance(ollama, OllamaAdapter):
        failures.append("routed Ollama candidate did not produce an Ollama adapter")
    else:
        for stream in (False, True):
            payload = ollama._payload(_request(), stream=stream)
            num_ctx = payload.get("options", {}).get("num_ctx")
            if num_ctx != planned_context_tokens:
                failures.append(
                    f"Ollama num_ctx diverged from routed context for stream={stream}"
                )

    return EvalOutcome(
        case_name="ollama_routed_context_matches_vram_admission",
        passed=not failures,
        detail="Ollama runtime context must equal the context used for VRAM admission",
        failures=tuple(failures),
    )


def _unbudgeted_ollama_does_not_invent_context_case() -> EvalOutcome:
    failures: list[str] = []
    adapter = OllamaAdapter("synthetic-local-q4")
    for stream in (False, True):
        payload = adapter._payload(_request(), stream=stream)
        if "num_ctx" in payload.get("options", {}):
            failures.append(
                f"low-level Ollama adapter invented an unreviewed context cap for stream={stream}"
            )

    return EvalOutcome(
        case_name="ollama_unbudgeted_context_not_invented",
        passed=not failures,
        detail="low-level adapters must not guess a context length without admission evidence",
        failures=tuple(failures),
    )


def run_ollama_context_parity_suite() -> list[EvalOutcome]:
    """Run local-only runtime-context parity regressions."""

    return [
        _routed_context_matches_ollama_runtime_case(),
        _unbudgeted_ollama_does_not_invent_context_case(),
    ]
