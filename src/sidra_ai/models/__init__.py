"""Replaceable local model backends. No paid API is ever required."""

from sidra_ai.models.base import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    ModelUnavailableError,
    estimate_tokens,
)
from sidra_ai.models.benchmark import (
    BenchmarkResult,
    UnsafeBenchmarkBackendError,
    run_benchmark,
)
from sidra_ai.models.budgeted import BudgetedLocalModelAdapter
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.models.hardware import (
    HardwareProbeError,
    VramSnapshot,
    probe_nvidia_vram,
    select_local_model_with_nvidia_probe,
)
from sidra_ai.models.http_backends import (
    LlamaCppAdapter,
    OllamaAdapter,
    TransformersAdapter,
)
from sidra_ai.models.registry import (
    BackendNotRegisteredError,
    PaidBackendRejectedError,
    adapter_from_settings,
    available_backends,
    create_adapter,
    register,
)

__all__ = [
    "BackendNotRegisteredError",
    "BenchmarkResult",
    "BudgetedLocalModelAdapter",
    "EchoModelAdapter",
    "GenerationChunk",
    "GenerationRequest",
    "GenerationResult",
    "HardwareProbeError",
    "LlamaCppAdapter",
    "LocalModelAdapter",
    "ModelUnavailableError",
    "OllamaAdapter",
    "PaidBackendRejectedError",
    "TransformersAdapter",
    "UnsafeBenchmarkBackendError",
    "VramSnapshot",
    "adapter_from_settings",
    "available_backends",
    "create_adapter",
    "estimate_tokens",
    "probe_nvidia_vram",
    "register",
    "run_benchmark",
    "select_local_model_with_nvidia_probe",
]
