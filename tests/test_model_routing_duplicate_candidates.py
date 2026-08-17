"""Fail-closed routing regressions for duplicate local model declarations."""

from __future__ import annotations

import pytest

from sidra_ai.models import routing
from sidra_ai.models.routing import HardwareBudget, LocalModelCandidate


def _candidate(*, weights_vram_mib: int, quantization: str, priority: int) -> LocalModelCandidate:
    return LocalModelCandidate(
        backend="echo",
        model="same-local-artifact",
        weights_vram_mib=weights_vram_mib,
        kv_cache_mib_per_1k_tokens=128,
        max_context_tokens=4096,
        quantization=quantization,
        priority=priority,
    )


def test_duplicate_route_ids_cannot_choose_optimistic_resource_metadata() -> None:
    """One route identity must not carry competing 6 GiB admission facts."""

    candidates = [
        _candidate(weights_vram_mib=1800, quantization="Q4", priority=1),
        _candidate(weights_vram_mib=6000, quantization="Q8", priority=100),
    ]

    with pytest.raises(ValueError, match="route IDs must be unique"):
        routing.select_local_model(
            candidates,
            hardware=HardwareBudget(vram_mib=6144, reserve_vram_mib=512),
            planned_context_tokens=2000,
        )


def test_duplicate_route_ids_fail_before_adapter_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ambiguous metadata is rejected before any local backend is started."""

    calls: list[tuple[object, ...]] = []

    def unexpected_create_adapter(*args, **kwargs):
        calls.append((*args, kwargs))
        raise AssertionError("adapter construction must not run")

    monkeypatch.setattr(routing, "create_adapter", unexpected_create_adapter)

    with pytest.raises(ValueError, match="route IDs must be unique"):
        routing.route_and_create_adapter(
            [
                _candidate(weights_vram_mib=1800, quantization="Q4", priority=1),
                _candidate(weights_vram_mib=1800, quantization="Q5", priority=2),
            ],
            hardware=HardwareBudget(vram_mib=6144, reserve_vram_mib=512),
            planned_context_tokens=2000,
        )

    assert calls == []
