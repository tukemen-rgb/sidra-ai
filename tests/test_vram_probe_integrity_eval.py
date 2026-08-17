"""Release-gate regression for local NVIDIA VRAM probe integrity."""

from __future__ import annotations

from sidra_ai.evals.vram_probe_integrity import run_vram_probe_integrity_suite


def test_vram_probe_integrity_release_gate_passes_offline() -> None:
    outcomes = run_vram_probe_integrity_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "vram_probe_single_row_binds_requested_device",
        "vram_probe_multi_row_fails_closed",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
