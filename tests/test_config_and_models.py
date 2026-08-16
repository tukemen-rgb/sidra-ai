"""Localhost-by-default, and no paid API anywhere in the dependency graph."""

from __future__ import annotations

import json

import pytest

from sidra_ai.config.settings import (
    DEFAULT_ALLOWED_REPOSITORIES,
    LOCALHOST_ADDRESSES,
    Settings,
    UnsafeConfigurationError,
    reset_settings_cache,
)
from sidra_ai.models.base import (
    GenerationRequest,
    LocalModelAdapter,
    ModelUnavailableError,
)
from sidra_ai.models.registry import (
    PaidBackendRejectedError,
    adapter_from_settings,
    available_backends,
    create_adapter,
    register,
)


# --- binding posture ---------------------------------------------------

def test_default_host_is_loopback() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.host in LOCALHOST_ADDRESSES
    assert settings.is_localhost_only


def test_default_from_env_is_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_settings_cache()
    assert Settings.from_env().is_localhost_only


def test_public_bind_is_refused_without_opt_in() -> None:
    with pytest.raises(UnsafeConfigurationError, match="non-loopback"):
        Settings(host="0.0.0.0").validate()


def test_public_bind_requires_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIDRA_API_TOKEN", raising=False)
    with pytest.raises(UnsafeConfigurationError, match="SIDRA_API_TOKEN"):
        Settings(host="0.0.0.0", allow_public_bind=True).validate()


def test_public_bind_allowed_with_opt_in_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", "a-locally-generated-value")
    Settings(host="0.0.0.0", allow_public_bind=True).validate()


def test_env_var_alone_cannot_expose_the_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting only the host must not be enough to go public."""

    monkeypatch.setenv("SIDRA_HOST", "0.0.0.0")
    reset_settings_cache()
    with pytest.raises(UnsafeConfigurationError):
        Settings.from_env()


def test_server_refuses_to_start_when_unsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    from sidra_ai.api import server

    monkeypatch.setenv("SIDRA_HOST", "0.0.0.0")
    reset_settings_cache()
    assert server.main([]) == 2


# --- secrets never live in settings ------------------------------------

def test_tokens_are_not_stored_in_the_settings_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", "super-secret-value")
    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "another-secret-value")
    reset_settings_cache()
    settings = Settings.from_env()

    assert "super-secret-value" not in repr(settings)
    assert "another-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.redacted_dict())
    assert settings.redacted_dict()["api_token_configured"] is True


def test_allowlist_defaults_to_the_five_sidra_repositories() -> None:
    assert set(DEFAULT_ALLOWED_REPOSITORIES) == {
        "tukemen-rgb/site",
        "tukemen-rgb/creater-yard",
        "tukemen-rgb/Fg",
        "tukemen-rgb/marketing",
        "tukemen-rgb/sidra-ai",
    }


def test_repository_allowlist_is_case_insensitive() -> None:
    assert Settings().is_repository_allowed("Tukemen-RGB/Site")
    assert not Settings().is_repository_allowed("tukemen-rgb/other")


# --- model backends ----------------------------------------------------

def test_default_backend_is_local_and_free() -> None:
    settings = Settings()
    assert settings.model_backend == "echo"
    adapter = adapter_from_settings(settings)
    assert adapter.requires_paid_api is False


def test_every_registered_backend_is_free() -> None:
    for name in available_backends():
        adapter_cls = create_adapter(name, "dummy").__class__
        assert adapter_cls.requires_paid_api is False, f"{name} bills per token"


def test_registry_refuses_a_paid_backend() -> None:
    """The constraint is structural: a paid adapter cannot be registered."""

    class PaidAdapter(LocalModelAdapter):
        backend = "some_paid_api"
        requires_paid_api = True

        def generate(self, request):  # pragma: no cover - never runs
            raise NotImplementedError

    with pytest.raises(PaidBackendRejectedError):
        register(PaidAdapter)
    assert "some_paid_api" not in available_backends()


def test_settings_reject_an_unknown_backend() -> None:
    with pytest.raises(UnsafeConfigurationError, match="not a local backend"):
        Settings(model_backend="openai").validate()


def test_remote_model_endpoint_is_refused_by_default() -> None:
    from sidra_ai.models.http_backends import OllamaAdapter

    with pytest.raises(ModelUnavailableError, match="not loopback"):
        OllamaAdapter("llama3", endpoint="http://inference.example.com:11434")


def test_remote_model_endpoint_cannot_be_enabled_with_ad_hoc_option() -> None:
    from sidra_ai.models.http_backends import OllamaAdapter

    with pytest.raises(ModelUnavailableError, match="does not allow remote"):
        OllamaAdapter(
            "llama3",
            endpoint="http://inference.example.com:11434",
            allow_remote_endpoint=True,
        )


def test_loopback_model_endpoint_is_accepted() -> None:
    from sidra_ai.models.http_backends import LlamaCppAdapter

    adapter = LlamaCppAdapter("local-32b", endpoint="http://127.0.0.1:8080")
    assert adapter.endpoint == "http://127.0.0.1:8080"


def test_echo_backend_works_without_weights_or_network() -> None:
    from sidra_ai.models.echo import EchoModelAdapter

    result = EchoModelAdapter().generate(
        GenerationRequest(system_prompt="s", user_message="what changed?")
    )
    assert result.text
    assert result.metadata["cost_usd"] == 0.0


def test_backends_are_swappable_through_one_interface() -> None:
    for name in available_backends():
        adapter = create_adapter(name, "model-name")
        assert isinstance(adapter, LocalModelAdapter)
        assert hasattr(adapter, "generate")
        assert hasattr(adapter, "generate_stream")


def test_non_streaming_backend_has_safe_single_chunk_fallback() -> None:
    from sidra_ai.models.echo import EchoModelAdapter

    adapter = EchoModelAdapter()
    request = GenerationRequest(system_prompt="s", user_message="q")
    chunks = list(adapter.generate_stream(request))

    assert len(chunks) == 1
    assert chunks[0].done is True
    assert chunks[0].text_delta
    assert chunks[0].backend == "echo"
    assert chunks[0].metadata["cost_usd"] == 0.0
    assert adapter.supports_streaming is False


def test_ollama_streams_ndjson_without_buffering_full_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sidra_ai.models.http_backends import OllamaAdapter

    adapter = OllamaAdapter("local-model")
    events = [
        json.dumps({"response": "Hel", "done": False}),
        json.dumps({"response": "lo", "done": False}),
        json.dumps(
            {
                "response": "",
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 2,
                "eval_duration": 100,
                "context": [1, 2, 3],
            }
        ),
    ]
    monkeypatch.setattr(adapter, "_stream_lines", lambda path, payload: iter(events))

    chunks = list(
        adapter.generate_stream(
            GenerationRequest(system_prompt="system", user_message="question")
        )
    )

    assert "".join(chunk.text_delta for chunk in chunks) == "Hello"
    assert chunks[-1].done is True
    assert chunks[-1].input_tokens_estimate == 12
    assert chunks[-1].output_tokens_estimate == 2
    assert chunks[-1].metadata["eval_duration"] == 100
    assert "context" not in chunks[-1].metadata
    assert adapter.supports_streaming is True


def test_llama_cpp_streams_sse_and_counts_returned_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sidra_ai.models.http_backends import LlamaCppAdapter

    adapter = LlamaCppAdapter("local-model")
    events = [
        ": keepalive",
        'data: {"content":"Hi","tokens":[10],"stop":false}',
        'data: {"content":"!","tokens":[11],"stop":true,"stop_type":"eos"}',
    ]
    monkeypatch.setattr(adapter, "_stream_lines", lambda path, payload: iter(events))

    chunks = list(
        adapter.generate_stream(
            GenerationRequest(system_prompt="system", user_message="question")
        )
    )

    assert "".join(chunk.text_delta for chunk in chunks) == "Hi!"
    assert chunks[-1].done is True
    assert chunks[-1].output_tokens_estimate == 2
    assert chunks[-1].finish_reason == "eos"
    assert adapter.supports_streaming is True


def test_stream_rejects_backend_error_event(monkeypatch: pytest.MonkeyPatch) -> None:
    from sidra_ai.models.http_backends import OllamaAdapter

    adapter = OllamaAdapter("local-model")
    monkeypatch.setattr(
        adapter,
        "_stream_lines",
        lambda path, payload: iter([json.dumps({"error": "generation failed"})]),
    )

    with pytest.raises(ModelUnavailableError, match="generation failed"):
        list(
            adapter.generate_stream(
                GenerationRequest(system_prompt="system", user_message="question")
            )
        )


def test_stream_requires_explicit_terminal_event(monkeypatch: pytest.MonkeyPatch) -> None:
    from sidra_ai.models.http_backends import LlamaCppAdapter

    adapter = LlamaCppAdapter("local-model")
    monkeypatch.setattr(
        adapter,
        "_stream_lines",
        lambda path, payload: iter(
            ['data: {"content":"partial","tokens":[1],"stop":false}']
        ),
    )

    with pytest.raises(ModelUnavailableError, match="terminal event"):
        list(
            adapter.generate_stream(
                GenerationRequest(system_prompt="system", user_message="question")
            )
        )


def test_local_benchmark_records_speed_memory_and_quantization_without_text() -> None:
    from sidra_ai.models.base import GenerationChunk, GenerationResult
    from sidra_ai.models.benchmark import run_benchmark

    class StreamingAdapter(LocalModelAdapter):
        backend = "fake_local"
        supports_streaming = True

        def generate(self, request: GenerationRequest) -> GenerationResult:
            raise AssertionError("native streaming path should be used")

        def generate_stream(self, request: GenerationRequest):
            yield GenerationChunk(
                text_delta="abc",
                backend=self.backend,
                model=self.model,
                output_tokens_estimate=3,
            )
            yield GenerationChunk(
                text_delta="def",
                backend=self.backend,
                model=self.model,
                done=True,
                input_tokens_estimate=10,
                output_tokens_estimate=6,
                finish_reason="stop",
            )

    adapter = StreamingAdapter("local-q4", quantization="Q4_K_M")
    times = iter([10.0, 10.5, 12.0])
    memory = iter([4096.0, 4608.0])
    request = GenerationRequest(
        system_prompt="PRIVATE SYSTEM",
        user_message="PRIVATE QUESTION",
        data_context="PRIVATE DATA",
    )
    result = run_benchmark(
        adapter,
        request,
        clock=lambda: next(times),
        memory_probe=lambda: next(memory),
    )

    assert result.time_to_first_token_s == 0.5
    assert result.total_time_s == 2.0
    assert result.output_tokens_estimate == 6
    assert result.output_tokens_per_second == 3.0
    assert result.memory_delta_mib == 512.0
    assert result.quantization == "Q4_K_M"
    serialized = json.dumps(result.to_dict())
    assert "PRIVATE SYSTEM" not in serialized
    assert "PRIVATE QUESTION" not in serialized
    assert "PRIVATE DATA" not in serialized
    assert result.to_dict()["external_api_cost_usd"] == 0.0


def test_local_benchmark_supports_dependency_free_non_streaming_backend() -> None:
    from sidra_ai.models.benchmark import run_benchmark
    from sidra_ai.models.echo import EchoModelAdapter

    adapter = EchoModelAdapter()
    times = iter([1.0, 1.25])
    result = run_benchmark(
        adapter,
        GenerationRequest(system_prompt="s", user_message="q"),
        clock=lambda: next(times),
    )

    assert result.backend == "echo"
    assert result.supports_streaming is False
    assert result.total_time_s == 0.25
    assert result.time_to_first_token_s == 0.25
    assert result.output_tokens_estimate > 0
    assert result.to_dict()["external_api_cost_usd"] == 0.0


def test_local_benchmark_refuses_paid_backend_even_if_constructed_directly() -> None:
    from sidra_ai.models.base import GenerationResult
    from sidra_ai.models.benchmark import UnsafeBenchmarkBackendError, run_benchmark

    class PaidAdapter(LocalModelAdapter):
        backend = "paid"
        requires_paid_api = True

        def generate(self, request: GenerationRequest) -> GenerationResult:
            raise AssertionError("paid adapter must never be invoked")

    with pytest.raises(UnsafeBenchmarkBackendError, match="paid backend"):
        run_benchmark(
            PaidAdapter("remote"),
            GenerationRequest(system_prompt="s", user_message="q"),
        )


def test_budget_wrapper_clamps_output_before_local_backend_call() -> None:
    from sidra_ai.models.base import GenerationResult
    from sidra_ai.models.budgeted import BudgetedLocalModelAdapter

    class RecordingAdapter(LocalModelAdapter):
        backend = "recording"

        def __init__(self) -> None:
            super().__init__("local")
            self.seen: GenerationRequest | None = None

        def generate(self, request: GenerationRequest) -> GenerationResult:
            self.seen = request
            return GenerationResult(text="ok", backend=self.backend, model=self.model)

    inner = RecordingAdapter()
    adapter = BudgetedLocalModelAdapter(
        inner, max_context_tokens=40, reserve_tokens=4
    )
    adapter.generate(
        GenerationRequest(
            system_prompt="system",
            user_message="question",
            max_output_tokens=100,
        )
    )

    assert inner.seen is not None
    assert 0 < inner.seen.max_output_tokens < 100


def test_budget_wrapper_fails_before_backend_on_oversized_input() -> None:
    from sidra_ai.models.base import GenerationResult
    from sidra_ai.models.budget import ContextWindowExceededError
    from sidra_ai.models.budgeted import BudgetedLocalModelAdapter

    class RecordingAdapter(LocalModelAdapter):
        backend = "recording"

        def __init__(self) -> None:
            super().__init__("local")
            self.calls = 0

        def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls += 1
            return GenerationResult(text="unsafe", backend=self.backend, model=self.model)

    inner = RecordingAdapter()
    adapter = BudgetedLocalModelAdapter(
        inner, max_context_tokens=8, reserve_tokens=2
    )

    with pytest.raises(ContextWindowExceededError, match="reduce input"):
        adapter.generate(
            GenerationRequest(
                system_prompt="system",
                user_message="x" * 100,
                max_output_tokens=4,
            )
        )
    assert inner.calls == 0


def test_registry_can_budget_wrap_any_registered_local_backend() -> None:
    from sidra_ai.models.budgeted import BudgetedLocalModelAdapter

    adapter = create_adapter(
        "echo",
        "sidra-local-v0",
        max_context_tokens=64,
        context_reserve_tokens=8,
    )

    assert isinstance(adapter, BudgetedLocalModelAdapter)
    assert adapter.backend == "echo"
    assert adapter.requires_paid_api is False
    assert adapter.health()["max_context_tokens"] == 64


def test_routed_adapter_cannot_exceed_vram_admitted_context_plan() -> None:
    """A route admitted for 2k context must not later accept an 8k-class request."""

    from sidra_ai.models.budget import ContextWindowExceededError
    from sidra_ai.models.routing import (
        HardwareBudget,
        LocalModelCandidate,
        route_and_create_adapter,
    )

    routed = route_and_create_adapter(
        [
            LocalModelCandidate(
                backend="echo",
                model="sidra-local-v0",
                weights_vram_mib=2048,
                kv_cache_mib_per_1k_tokens=128,
                max_context_tokens=8192,
                quantization="Q4_K_M",
            )
        ],
        hardware=HardwareBudget(vram_mib=6144, reserve_vram_mib=512),
        planned_context_tokens=2000,
        adapter_options={"context_reserve_tokens": 128},
    )

    assert routed.decision.candidate.max_context_tokens == 8192
    assert routed.decision.planned_context_tokens == 2000
    assert routed.adapter.health()["max_context_tokens"] == 2000

    with pytest.raises(ContextWindowExceededError, match="reduce input"):
        routed.adapter.generate(
            GenerationRequest(
                system_prompt="system",
                user_message="x" * 9000,
                max_output_tokens=64,
            )
        )


def test_observed_nvidia_vram_drives_route_admission() -> None:
    import subprocess

    from sidra_ai.models.hardware import select_local_model_with_nvidia_probe
    from sidra_ai.models.routing import LocalModelCandidate

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout="6144, 3000\n",
            stderr="",
        )

    decision = select_local_model_with_nvidia_probe(
        [
            LocalModelCandidate(
                backend="echo",
                model="sidra-local-v0",
                weights_vram_mib=2100,
                kv_cache_mib_per_1k_tokens=128,
                max_context_tokens=4096,
                quantization="Q4_K_M",
            )
        ],
        planned_context_tokens=2000,
        reserve_vram_mib=512,
        runner=runner,
    )

    assert decision.usable_vram_mib == 2488
    assert decision.required_vram_mib == 2356
    assert decision.candidate.model == "sidra-local-v0"


def test_nvidia_probe_failure_never_falls_back_to_static_vram_budget() -> None:
    from sidra_ai.models.hardware import HardwareProbeError, select_local_model_with_nvidia_probe
    from sidra_ai.models.routing import LocalModelCandidate

    def runner(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    with pytest.raises(HardwareProbeError, match="unavailable"):
        select_local_model_with_nvidia_probe(
            [
                LocalModelCandidate(
                    backend="echo",
                    model="would-fit-static-budget",
                    weights_vram_mib=4096,
                    kv_cache_mib_per_1k_tokens=128,
                    max_context_tokens=4096,
                )
            ],
            planned_context_tokens=1000,
            runner=runner,
        )


def test_no_paid_llm_sdk_is_a_dependency() -> None:
    """A paid SDK must never appear in pyproject dependencies."""

    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    required = " ".join(data["project"]["dependencies"]).lower()
    for banned in ("openai", "anthropic", "google-generativeai", "cohere", "mistralai"):
        assert banned not in required, f"{banned} must not be a required dependency"
