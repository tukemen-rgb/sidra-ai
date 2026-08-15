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
from sidra_ai.models.echo import EchoModelAdapter
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
    "EchoModelAdapter",
    "GenerationChunk",
    "GenerationRequest",
    "GenerationResult",
    "LlamaCppAdapter",
    "LocalModelAdapter",
    "ModelUnavailableError",
    "OllamaAdapter",
    "PaidBackendRejectedError",
    "TransformersAdapter",
    "UnsafeBenchmarkBackendError",
    "adapter_from_settings",
    "available_backends",
    "create_adapter",
    "estimate_tokens",
    "register",
    "run_benchmark",
]
