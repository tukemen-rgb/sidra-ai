"""Deterministic, local-only model routing for constrained hardware.

Routing deliberately does *not* guess model memory requirements. Each model
candidate must carry measurements or conservative estimates from a local
benchmark/model manifest. Unknown memory cost is rejected by default so a new
model cannot accidentally turn a 6 GiB machine into an OOM loop.

The router is pure policy: it performs no network calls and starts no model
process. Only after a candidate has been selected is the existing registry
asked to construct its :class:`~sidra_ai.models.base.LocalModelAdapter`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

from sidra_ai.models.base import LocalModelAdapter
from sidra_ai.models.registry import available_backends, create_adapter

MiB = 1024 * 1024


class NoLocalModelRouteError(RuntimeError):
    """Raised when no candidate can safely run inside the supplied budget."""


@dataclass(frozen=True)
class HardwareBudget:
    """Memory budget used by the router.

    ``vram_mib`` is physical GPU memory. ``reserve_vram_mib`` is intentionally
    not offered to model weights/KV cache; it protects the display driver,
    runtime allocations and estimation error. A 6 GiB card therefore has a
    smaller *model* budget than 6144 MiB.

    System RAM is optional. Leaving it at zero disables CPU-offload routes,
    which is safer than assuming host memory exists.
    """

    vram_mib: int = 6144
    ram_mib: int = 0
    reserve_vram_mib: int = 512
    reserve_ram_mib: int = 2048

    def __post_init__(self) -> None:
        if self.vram_mib <= 0:
            raise ValueError("vram_mib must be positive")
        if self.ram_mib < 0:
            raise ValueError("ram_mib cannot be negative")
        if self.reserve_vram_mib < 0 or self.reserve_vram_mib >= self.vram_mib:
            raise ValueError("reserve_vram_mib must leave usable VRAM")
        if self.reserve_ram_mib < 0:
            raise ValueError("reserve_ram_mib cannot be negative")

    @property
    def usable_vram_mib(self) -> int:
        return self.vram_mib - self.reserve_vram_mib

    @property
    def usable_ram_mib(self) -> int:
        return max(0, self.ram_mib - self.reserve_ram_mib)


@dataclass(frozen=True)
class LocalModelCandidate:
    """A model/backend pair with explicit resource metadata.

    Memory numbers must come from a benchmark or a conservative model manifest;
    the router never infers them from parameter count or model name.
    ``weights_vram_mib=None`` means "not measured" and is rejected by default.

    ``kv_cache_mib_per_1k_tokens`` makes context length part of the admission
    decision. This avoids the common failure where quantized weights fit in
    VRAM but a long context causes an out-of-memory allocation.
    """

    backend: str
    model: str
    weights_vram_mib: int | None
    kv_cache_mib_per_1k_tokens: int = 0
    max_context_tokens: int = 4096
    supports_cpu_offload: bool = False
    offload_ram_mib: int = 0
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.backend.strip() or not self.model.strip():
            raise ValueError("backend and model are required")
        if self.weights_vram_mib is not None and self.weights_vram_mib <= 0:
            raise ValueError("weights_vram_mib must be positive when supplied")
        if self.kv_cache_mib_per_1k_tokens < 0:
            raise ValueError("kv_cache_mib_per_1k_tokens cannot be negative")
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive")
        if self.offload_ram_mib < 0:
            raise ValueError("offload_ram_mib cannot be negative")

    @property
    def route_id(self) -> str:
        return f"{self.backend}:{self.model}"

    def required_vram_mib(self, context_tokens: int) -> int | None:
        if self.weights_vram_mib is None:
            return None
        context_k = math.ceil(max(0, context_tokens) / 1000)
        return self.weights_vram_mib + context_k * self.kv_cache_mib_per_1k_tokens


RouteMode = Literal["gpu", "cpu_offload"]


@dataclass(frozen=True)
class RejectedRoute:
    route_id: str
    reason: str


@dataclass(frozen=True)
class RouteDecision:
    candidate: LocalModelCandidate
    mode: RouteMode
    required_vram_mib: int
    rejected: tuple[RejectedRoute, ...]

    @property
    def reason(self) -> str:
        if self.mode == "gpu":
            return (
                f"{self.candidate.route_id} fits the VRAM budget "
                f"({self.required_vram_mib} <= selected limit)"
            )
        return (
            f"{self.candidate.route_id} exceeds the direct VRAM budget but "
            "explicitly supports CPU offload within the supplied RAM budget"
        )


@dataclass(frozen=True)
class RoutedAdapter:
    decision: RouteDecision
    adapter: LocalModelAdapter


def select_local_model(
    candidates: Sequence[LocalModelCandidate],
    *,
    hardware: HardwareBudget,
    context_tokens: int,
) -> RouteDecision:
    """Select the safest highest-priority local route that fits the budget.

    Selection order is deterministic:

    1. lower ``priority`` value wins;
    2. direct-GPU routes win over CPU-offload at equal priority;
    3. lower calculated VRAM demand wins as the final tie-breaker.

    Unregistered backends are rejected, so routing cannot silently introduce a
    paid/external provider outside the local-only registry.
    """

    if context_tokens < 0:
        raise ValueError("context_tokens cannot be negative")

    registered = set(available_backends())
    accepted: list[tuple[int, int, int, LocalModelCandidate, RouteMode]] = []
    rejected: list[RejectedRoute] = []

    for candidate in candidates:
        if candidate.backend not in registered:
            rejected.append(
                RejectedRoute(candidate.route_id, "backend is not in the local-only registry")
            )
            continue

        if context_tokens > candidate.max_context_tokens:
            rejected.append(
                RejectedRoute(
                    candidate.route_id,
                    f"context {context_tokens} exceeds declared maximum "
                    f"{candidate.max_context_tokens}",
                )
            )
            continue

        required_vram = candidate.required_vram_mib(context_tokens)
        if required_vram is None:
            rejected.append(
                RejectedRoute(candidate.route_id, "VRAM requirement is unknown")
            )
            continue

        if required_vram <= hardware.usable_vram_mib:
            accepted.append((candidate.priority, 0, required_vram, candidate, "gpu"))
            continue

        if not candidate.supports_cpu_offload:
            rejected.append(
                RejectedRoute(
                    candidate.route_id,
                    f"requires {required_vram} MiB VRAM; only "
                    f"{hardware.usable_vram_mib} MiB is available",
                )
            )
            continue

        if candidate.offload_ram_mib <= 0:
            rejected.append(
                RejectedRoute(
                    candidate.route_id,
                    "CPU offload is declared but offload RAM cost is unknown",
                )
            )
            continue

        if candidate.offload_ram_mib > hardware.usable_ram_mib:
            rejected.append(
                RejectedRoute(
                    candidate.route_id,
                    f"CPU offload needs {candidate.offload_ram_mib} MiB RAM; only "
                    f"{hardware.usable_ram_mib} MiB is available",
                )
            )
            continue

        accepted.append(
            (candidate.priority, 1, required_vram, candidate, "cpu_offload")
        )

    if not accepted:
        details = "; ".join(f"{item.route_id}: {item.reason}" for item in rejected)
        raise NoLocalModelRouteError(
            "no local model candidate fits the declared hardware/context budget"
            + (f" ({details})" if details else "")
        )

    _, _, required_vram, selected, mode = min(
        accepted, key=lambda item: (item[0], item[1], item[2], item[3].route_id)
    )
    return RouteDecision(
        candidate=selected,
        mode=mode,
        required_vram_mib=required_vram,
        rejected=tuple(rejected),
    )


def route_and_create_adapter(
    candidates: Sequence[LocalModelCandidate],
    *,
    hardware: HardwareBudget,
    context_tokens: int,
    adapter_options: dict[str, object] | None = None,
) -> RoutedAdapter:
    """Route first, then construct exactly one local adapter.

    No model is loaded and no endpoint is contacted during routing. Adapter
    options are supplied only to the selected backend.
    """

    decision = select_local_model(
        candidates, hardware=hardware, context_tokens=context_tokens
    )
    adapter = create_adapter(
        decision.candidate.backend,
        decision.candidate.model,
        **(adapter_options or {}),
    )
    return RoutedAdapter(decision=decision, adapter=adapter)
