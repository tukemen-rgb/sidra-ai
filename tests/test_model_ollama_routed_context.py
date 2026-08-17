"""Keep Ollama runtime context allocation aligned with VRAM admission."""

from sidra_ai.models.base import GenerationRequest
from sidra_ai.models.budgeted import BudgetedLocalModelAdapter
from sidra_ai.models.http_backends import OllamaAdapter
from sidra_ai.models.registry import create_adapter
from sidra_ai.models.routing import (
    HardwareBudget,
    LocalModelCandidate,
    route_and_create_adapter,
)
from sidra_ai.models.singleflight import SingleFlightLocalModelAdapter


def _request() -> GenerationRequest:
    return GenerationRequest(system_prompt="system", user_message="question")


def test_budgeted_ollama_payload_uses_same_context_cap() -> None:
    adapter = create_adapter(
        "ollama",
        "local-q4",
        max_context_tokens=2048,
    )

    assert isinstance(adapter, BudgetedLocalModelAdapter)
    assert isinstance(adapter.inner, OllamaAdapter)
    assert adapter.max_context_tokens == 2048

    payload = adapter.inner._payload(_request(), stream=False)
    assert payload["options"]["num_ctx"] == 2048
    assert payload["options"]["num_predict"] == _request().max_output_tokens


def test_routed_ollama_pins_runtime_context_to_vram_admission() -> None:
    candidate = LocalModelCandidate(
        backend="ollama",
        model="local-q4",
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
        planned_context_tokens=2048,
    )

    assert routed.decision.planned_context_tokens == 2048
    assert isinstance(routed.adapter, SingleFlightLocalModelAdapter)
    budgeted = routed.adapter.inner
    assert isinstance(budgeted, BudgetedLocalModelAdapter)
    assert budgeted.max_context_tokens == 2048
    assert isinstance(budgeted.inner, OllamaAdapter)

    payload = budgeted.inner._payload(_request(), stream=True)
    assert payload["options"]["num_ctx"] == routed.decision.planned_context_tokens


def test_unbudgeted_low_level_ollama_does_not_invent_context_cap() -> None:
    adapter = OllamaAdapter("local-q4")
    payload = adapter._payload(_request(), stream=False)

    assert "num_ctx" not in payload["options"]
