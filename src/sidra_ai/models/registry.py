"""Backend registry.

The registry is the enforcement point for "no required paid LLM API": a
backend whose ``requires_paid_api`` is ``True`` cannot be registered, so the
constraint cannot be violated by adding a file - it fails at import time.

v0.1 also refuses local backends that can still trigger runtime downloads.
Those backends remain visible in source for future work, but they are not
selectable until their artifact-loading path is fail-closed and offline-only.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from sidra_ai.config.settings import Settings, get_settings
from sidra_ai.models.base import LocalModelAdapter, ModelUnavailableError
from sidra_ai.models.budgeted import BudgetedLocalModelAdapter
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.models.http_backends import (
    LlamaCppAdapter,
    OllamaAdapter,
    TransformersAdapter,
)
from sidra_ai.models.llama_runtime import LlamaCppRuntimeGuard


class BackendNotRegisteredError(KeyError):
    """Raised when configuration names a backend that does not exist."""


class PaidBackendRejectedError(RuntimeError):
    """Raised when a backend that bills per token is offered to the registry."""


_REGISTRY: dict[str, type[LocalModelAdapter]] = {}

_DEFERRED_BACKENDS: dict[str, str] = {
    "transformers": (
        "disabled in SIDRA AI v0.1 until the adapter accepts only a pre-staged "
        "local model artifact and cannot download model code or weights at runtime"
    ),
}


def register(adapter_cls: type[LocalModelAdapter]) -> type[LocalModelAdapter]:
    """Register a local backend. Paid backends are refused."""

    if getattr(adapter_cls, "requires_paid_api", False):
        raise PaidBackendRejectedError(
            f"{adapter_cls.__name__} requires a paid API; SIDRA AI v0.1 runs on "
            "local backends only"
        )
    _REGISTRY[adapter_cls.backend] = adapter_cls
    return adapter_cls


# TransformersAdapter stays importable for focused development/tests, but it is
# intentionally not registered in v0.1. Its current pipeline(model=<name>) path
# may resolve a Hub model identifier and download artifacts at runtime. Normal
# SIDRA adapter selection must fail closed until local-artifact-only loading is
# implemented and verified.
for _cls in (EchoModelAdapter, OllamaAdapter, LlamaCppAdapter):
    register(_cls)


def available_backends() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def registry_view() -> Mapping[str, type[LocalModelAdapter]]:
    return dict(_REGISTRY)


def create_adapter(
    backend: str, model: str, **options: Any
) -> LocalModelAdapter:
    """Instantiate a registered backend by name.

    Supplying ``max_context_tokens`` activates the same fail-closed token
    budget wrapper for every registered local backend. The value must come
    from an explicit model manifest or measurement; this factory never infers
    it from a model name or parameter count.

    A caller that owns a verified tokenizer for the admitted local runtime may
    also pass ``input_token_counter``. The callback is consumed by the generic
    budget wrapper rather than forwarded into a backend, keeping exact token
    counting optional and model/runtime neutral. Without the callback, SIDRA's
    conservative local estimator remains in force.

    The admitted context cap is also retained in the inner adapter options so
    local backends use the same runtime context assumption that routing used
    for KV-cache admission. Ollama receives the cap directly as ``num_ctx``;
    routed llama.cpp adapters verify the live server's read-only ``/props``
    context and slot configuration before every generation.
    """

    max_context_tokens = options.get("max_context_tokens")
    reserve_tokens = options.pop("context_reserve_tokens", 128)
    min_output_tokens = options.pop("min_output_tokens", 1)
    input_token_counter = options.pop("input_token_counter", None)

    if max_context_tokens is None and (
        reserve_tokens != 128
        or min_output_tokens != 1
        or input_token_counter is not None
    ):
        raise ValueError(
            "context_reserve_tokens/min_output_tokens/input_token_counter require "
            "max_context_tokens"
        )

    try:
        adapter_cls = _REGISTRY[backend]
    except KeyError as exc:
        deferred_reason = _DEFERRED_BACKENDS.get(backend)
        if deferred_reason is not None:
            raise BackendNotRegisteredError(
                f"model backend {backend!r} is temporarily {deferred_reason}"
            ) from exc
        raise BackendNotRegisteredError(
            f"unknown model backend {backend!r}; available: {available_backends()}"
        ) from exc

    adapter = adapter_cls(model, **options)
    if max_context_tokens is None:
        return adapter

    context_cap = int(max_context_tokens)
    if backend == "llama_cpp":
        adapter = LlamaCppRuntimeGuard(
            adapter,
            expected_context_tokens=context_cap,
        )

    return BudgetedLocalModelAdapter(
        adapter,
        max_context_tokens=context_cap,
        reserve_tokens=int(reserve_tokens),
        min_output_tokens=int(min_output_tokens),
        input_token_counter=input_token_counter,
    )


def adapter_from_settings(settings: Settings | None = None) -> LocalModelAdapter:
    """Build only the dependency-free baseline adapter from configuration.

    Real local backends must pass reviewed-manifest and freshly observed-VRAM
    admission before construction. Keeping this convenience helper echo-only
    prevents library/embedding callers from bypassing the same 6 GiB safety
    boundary that the real SIDRA API composition path enforces.
    """

    settings = settings or get_settings()
    if settings.model_backend != "echo":
        raise ModelUnavailableError(
            "non-echo local models require reviewed-manifest and observed-VRAM admission"
        )

    options: dict[str, Any] = {}
    if settings.model_endpoint:
        options["endpoint"] = settings.model_endpoint
    return create_adapter(settings.model_backend, settings.model_name, **options)


#: Convenience for tests and callers that want an explicit no-op backend.
default_adapter: Callable[[], LocalModelAdapter] = lambda: EchoModelAdapter()
