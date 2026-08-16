from __future__ import annotations

import pytest

from sidra_ai.models.base import LocalModelAdapter
from sidra_ai.models.routing import (
    HardwareBudget,
    LocalModelCandidate,
    NoLocalModelRouteError,
    route_and_create_adapter,
    select_local_model,
)


def test_6gb_budget_keeps_vram_headroom() -> None:
    hardware = HardwareBudget()
    assert hardware.vram_mib == 6144
    assert hardware.usable_vram_mib == 5632


def test_router_rejects_unknown_memory_cost() -> None:
    candidate = LocalModelCandidate(
        backend="echo",
        model="unmeasured",
        weights_vram_mib=None,
    )
    with pytest.raises(NoLocalModelRouteError, match="VRAM requirement is unknown"):
        select_local_model([candidate], hardware=HardwareBudget(), context_tokens=1000)


def test_router_skips_high_priority_candidate_that_would_oom() -> None:
    too_large = LocalModelCandidate(
        backend="echo",
        model="large",
        weights_vram_mib=6000,
        priority=1,
    )
    fits = LocalModelCandidate(
        backend="echo",
        model="small",
        weights_vram_mib=4000,
        priority=10,
    )
    decision = select_local_model(
        [too_large, fits], hardware=HardwareBudget(), context_tokens=1000
    )
    assert decision.candidate.model == "small"
    assert decision.mode == "gpu"
    assert any(item.route_id.endswith(":large") for item in decision.rejected)


def test_context_kv_cache_is_part_of_the_vram_admission_check() -> None:
    candidate = LocalModelCandidate(
        backend="echo",
        model="context-sensitive",
        weights_vram_mib=5200,
        kv_cache_mib_per_1k_tokens=150,
        max_context_tokens=8000,
    )

    short = select_local_model(
        [candidate], hardware=HardwareBudget(), context_tokens=2000
    )
    assert short.required_vram_mib == 5500

    with pytest.raises(NoLocalModelRouteError, match="requires 5800 MiB VRAM"):
        select_local_model(
            [candidate], hardware=HardwareBudget(), context_tokens=4000
        )


def test_context_larger_than_declared_window_is_rejected() -> None:
    candidate = LocalModelCandidate(
        backend="echo",
        model="short-context",
        weights_vram_mib=1000,
        max_context_tokens=4096,
    )
    with pytest.raises(NoLocalModelRouteError, match="exceeds declared maximum"):
        select_local_model(
            [candidate], hardware=HardwareBudget(), context_tokens=5000
        )


def test_cpu_offload_requires_explicit_capability_and_ram_budget() -> None:
    candidate = LocalModelCandidate(
        backend="echo",
        model="offloadable",
        weights_vram_mib=7000,
        supports_cpu_offload=True,
        offload_ram_mib=12000,
    )

    with pytest.raises(NoLocalModelRouteError, match="only 0 MiB is available"):
        select_local_model(
            [candidate], hardware=HardwareBudget(ram_mib=0), context_tokens=1000
        )

    decision = select_local_model(
        [candidate],
        hardware=HardwareBudget(ram_mib=32768),
        context_tokens=1000,
    )
    assert decision.mode == "cpu_offload"


def test_unregistered_backend_cannot_enter_the_route() -> None:
    candidate = LocalModelCandidate(
        backend="paid-cloud-provider",
        model="remote-model",
        weights_vram_mib=1,
    )
    with pytest.raises(NoLocalModelRouteError, match="local-only registry"):
        select_local_model([candidate], hardware=HardwareBudget(), context_tokens=1)


def test_equal_priority_prefers_direct_gpu_over_offload() -> None:
    offload = LocalModelCandidate(
        backend="echo",
        model="offload",
        weights_vram_mib=7000,
        supports_cpu_offload=True,
        offload_ram_mib=10000,
        priority=5,
    )
    gpu = LocalModelCandidate(
        backend="echo",
        model="gpu",
        weights_vram_mib=5000,
        priority=5,
    )
    decision = select_local_model(
        [offload, gpu],
        hardware=HardwareBudget(ram_mib=32768),
        context_tokens=1000,
    )
    assert decision.candidate.model == "gpu"
    assert decision.mode == "gpu"


def test_route_then_create_constructs_only_selected_local_adapter() -> None:
    candidate = LocalModelCandidate(
        backend="echo",
        model="selected",
        weights_vram_mib=100,
    )
    routed = route_and_create_adapter(
        [candidate], hardware=HardwareBudget(), context_tokens=1000
    )
    assert routed.decision.candidate.model == "selected"
    assert isinstance(routed.adapter, LocalModelAdapter)
    assert routed.adapter.backend == "echo"
