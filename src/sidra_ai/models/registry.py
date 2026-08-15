"""Backend registry.

The registry is the enforcement point for "no required paid LLM API": a
backend whose ``requires_paid_api`` is ``True`` cannot be registered, so the
constraint cannot be violated by adding a file - it fails at import time.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from sidra_ai.config.settings import Settings, get_settings
from sidra_ai.models.base import LocalModelAdapter
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.models.http_backends import (
    LlamaCppAdapter,
    OllamaAdapter,
    TransformersAdapter,
)


class BackendNotRegisteredError(KeyError):
    """Raised when configuration names a backend that does not exist."""


class PaidBackendRejectedError(RuntimeError):
    """Raised when a backend that bills per token is offered to the registry."""


_REGISTRY: dict[str, type[LocalModelAdapter]] = {}


def register(adapter_cls: type[LocalModelAdapter]) -> type[LocalModelAdapter]:
    """Register a local backend. Paid backends are refused."""

    if getattr(adapter_cls, "requires_paid_api", False):
        raise PaidBackendRejectedError(
            f"{adapter_cls.__name__} requires a paid API; SIDRA AI v0.1 runs on "
            "local backends only"
        )
    _REGISTRY[adapter_cls.backend] = adapter_cls
    return adapter_cls


for _cls in (EchoModelAdapter, OllamaAdapter, LlamaCppAdapter, TransformersAdapter):
    register(_cls)


def available_backends() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def registry_view() -> Mapping[str, type[LocalModelAdapter]]:
    return dict(_REGISTRY)


def create_adapter(
    backend: str, model: str, **options: Any
) -> LocalModelAdapter:
    """Instantiate a registered backend by name."""

    try:
        adapter_cls = _REGISTRY[backend]
    except KeyError as exc:
        raise BackendNotRegisteredError(
            f"unknown model backend {backend!r}; available: {available_backends()}"
        ) from exc
    return adapter_cls(model, **options)


def adapter_from_settings(settings: Settings | None = None) -> LocalModelAdapter:
    """Build the adapter described by configuration."""

    settings = settings or get_settings()
    options: dict[str, Any] = {}
    if settings.model_endpoint:
        options["endpoint"] = settings.model_endpoint
    return create_adapter(settings.model_backend, settings.model_name, **options)


#: Convenience for tests and callers that want an explicit no-op backend.
default_adapter: Callable[[], LocalModelAdapter] = lambda: EchoModelAdapter()
