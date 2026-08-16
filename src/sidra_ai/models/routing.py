"""Deterministic local-model routing for constrained hardware.

The router is pure policy: it never starts a model process and never makes a
network request. Memory and context requirements must come from measurements or
a conservative local manifest; they are never inferred from parameter count or
model name.

v0.1 deliberately admits direct-GPU routes only. CPU-offload semantics differ
by backend and are not yet represented by the common adapter interface, so
pretending that a generic route can enable offload would make an OOM decision
look safer than it really is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from sidra_ai.models.base import LocalModelAdapter
from sidra_ai.models.registry import available_backends, create_adapter
from sidra_ai.models.singleflight import SingleFlightLocalModelAdapter


class NoLocalModelRouteError(RuntimeError):
    """Raised when no candidate safely fits the declared hardware budget."""


@dataclass(frozen=True)
class HardwareBudget:
    """Owned accelerator budget used for route admission.

    Defaults model the current 6 GiB-class starting point. A fixed reserve is
    kept away from model weights/KV cache for runtime allocations, display use,
    and estimation error.

    ``observed_free_vram_mib`` is an optional snapshot supplied by the caller
    immediately before routing. When present, admission uses the smaller of the
    configured budget and the observed free VRAM after applying the same safety
    reserve. The router deliberately does not probe the GPU itself so policy
    remains deterministic and backend/vendor independent.
    """

    vram_mib: int = 6144
    reserve_vram_mib: int = 512
    observed_free_vram_mib: int | None = None

    def __post_init__(self) -> None:
        if self.vram_mib <= 0:
            raise ValueError("vram_mib must be positive")
        if self.reserve_vram_mib < 0 or self.reserve_vram_mib >= self.vram_mib:
            raise ValueError("reserve_vram_mib must leave usable VRAM")
        if self.observed_free_vram_mib is not None and self.observed_free_vram_mib <= 0:
            raise ValueError("observed_free_vram_mib must be positive when supplied")

    @property
    def usable_vram_mib(self) -> int:
        configured_usable = self.vram_mib - self.reserve_vram_mib
        if self.observed_free_vram_mib is None:
            return configured_usable

        observed_usable = max(0, self.observed_free_vram_mib - self.reserve_vram_mib)
        return min(configured_usable, observed_usable)


@dataclass(frozen=True)
class LocalModelCandidate:
    """One local backend/model candidate with explicit resource metadata."""

    backend: str
    model: str
    weights_vram_mib: int | None
    kv_cache_mib_per_1k_tokens: int | None = None
    max_context_tokens: int = 4096
    quantization: str = "unknown"
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.backend.strip() or not self.model.strip():
            raise ValueError("backend and model are required")
        if self.weights_vram_mib is not None and self.weights_vram_mib <= 0:
            raise ValueError("weights_vram_mib must be positive when supplied")
        if (
            self.kv_cache_mib_per_1k_tokens is not None
            and self.kv_cache_mib_per_1k_tokens < 0
        ):
            raise ValueError("kv_cache_mib_per_1k_tokens cannot be negative")
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive")

    @property
    def route_id(self) -> str:
        return f"{self.backend}:{self.model}"

    def required_vram_mib(self, planned_context_tokens: int) -> int | None:
        """Return declared weight + KV-cache demand for the planned context.

        Missing KV-cache metadata is treated as unknown rather than as zero.
        On a 6 GiB-class device, assuming an omitted KV cost is free can admit a
        model that fits weights but OOMs once context is allocated.
        """

        if self.weights_vram_mib is None or self.kv_cache_mib_per_1k_tokens is None:
            return None
        context_k = math.ceil(max(0, planned_context_tokens) / 1000)
        return self.weights_vram_mib + context_k * self.kv_cache_mib_per_1k_tokens


@dataclass(frozen=True)
class RejectedRoute:
    route_id: str
    reason: str


@dataclass(frozen=True)
class RouteDecision:
    candidate: LocalModelCandidate
    required_vram_mib: int
    usable_vram_mib: int
    planned_context_tokens: int
    rejected: tuple[RejectedRoute, ...]


@dataclass(frozen=True)
class RoutedAdapter:
    decision: RouteDecision
    adapter: LocalModelAdapter


def select_local_model(
    candidates: Sequence[LocalModelCandidate],
    *,
    hardware: HardwareBudget,
    planned_context_tokens: int,
) -> RouteDecision:
    """Select the safest highest-priority direct-GPU candidate.

    The caller supplies the *planned total context* used for KV-cache admission.
    The exact value is retained in the decision so downstream audit/benchmark
    code can verify the assumption that admitted the route. Request-level
    budgeting remains enforced independently by :class:`BudgetedLocalModelAdapter`
    after a route is selected.
    """

    if planned_context_tokens < 0:
        raise ValueError("planned_context_tokens cannot be negative")

    registered = set(available_backends())
    accepted: list[tuple[int, int, str, LocalModelCandidate]] = []
    rejected: list[RejectedRoute] = []

    for candidate in candidates:
        if candidate.backend not in registered:
            rejected.append(
                RejectedRoute(candidate.route_id, "backend is not in the local-only registry")
            )
            continue

        if planned_context_tokens > candidate.max_context_tokens:
            rejected.append(
                RejectedRoute(
                    candidate.route_id,
                    f"planned context {planned_context_tokens} exceeds declared maximum "
                    f"{candidate.max_context_tokens}",
                )
            )
            continue

        required_vram = candidate.required_vram_mib(planned_context_tokens)
        if required_vram is None:
            rejected.append(RejectedRoute(candidate.route_id, "VRAM requirement is unknown"))
            continue

        if required_vram > hardware.usable_vram_mib:
            rejected.append(
                RejectedRoute(
                    candidate.route_id,
                    f"requires {required_vram} MiB VRAM; only "
                    f"{hardware.usable_vram_mib} MiB is available",
                )
            )
            continue

        accepted.append((candidate.priority, required_vram, candidate.route_id, candidate))

    if not accepted:
        details = "; ".join(f"{item.route_id}: {item.reason}" for item in rejected)
        raise NoLocalModelRouteError(
            "no local model candidate fits the declared hardware/context budget"
            + (f" ({details})" if details else "")
        )

    _, required_vram, _, selected = min(accepted)
    return RouteDecision(
        candidate=selected,
        required_vram_mib=required_vram,
        usable_vram_mib=hardware.usable_vram_mib,
        planned_context_tokens=planned_context_tokens,
        rejected=tuple(rejected),
    )


def route_and_create_adapter(
    candidates: Sequence[LocalModelCandidate],
    *,
    hardware: HardwareBudget,
    planned_context_tokens: int,
    adapter_options: dict[str, Any] | None = None,
) -> RoutedAdapter:
    """Route first, then construct one budget-enforced local adapter.

    ``planned_context_tokens`` is not only an admission hint. It is the maximum
    runtime context allowed for this routed adapter, because the VRAM decision
    was calculated from that KV-cache budget. A caller that needs a larger
    context must route again with the larger plan instead of silently using the
    candidate's wider architectural context window.

    Callers cannot override ``max_context_tokens`` through adapter options; the
    route decision remains the source of truth. After construction, the router
    also verifies that the adapter actually exposes the admitted cap. This
    catches future registry/backend refactors that accidentally drop budgeting
    before an oversized request reaches a 6GB-class device.

    The admitted VRAM budget describes one active generation context. v0.1
    therefore wraps routed adapters in a fail-fast single-flight guard so two
    simultaneous requests cannot allocate a second KV cache and invalidate the
    memory assumption that admitted the route.
    """

    if planned_context_tokens <= 0:
        raise ValueError("planned_context_tokens must be positive when creating an adapter")

    decision = select_local_model(
        candidates,
        hardware=hardware,
        planned_context_tokens=planned_context_tokens,
    )
    options = dict(adapter_options or {})
    if "max_context_tokens" in options:
        raise ValueError("max_context_tokens comes from the route decision")

    adapter = create_adapter(
        decision.candidate.backend,
        decision.candidate.model,
        max_context_tokens=planned_context_tokens,
        **options,
    )
    if adapter.requires_paid_api:
        raise NoLocalModelRouteError("selected adapter unexpectedly requires a paid API")

    adapter = SingleFlightLocalModelAdapter(adapter)
    runtime_cap = getattr(adapter, "max_context_tokens", None)
    if runtime_cap != decision.planned_context_tokens:
        raise NoLocalModelRouteError(
            "selected adapter did not enforce the context cap used for VRAM admission"
        )
    return RoutedAdapter(decision=decision, adapter=adapter)
