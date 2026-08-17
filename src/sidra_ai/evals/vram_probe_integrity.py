"""Offline release regressions for NVIDIA VRAM probe integrity.

The model admission path routes 6 GiB-class local models against one fresh
``nvidia-smi`` observation. These evals independently protect the cardinality
boundary: one requested device must yield exactly one non-empty result row.
Ambiguous multi-row output must fail closed instead of letting routing select an
arbitrary device-memory observation.

No real GPU, subprocess, model, socket, or network access is used here.
"""

from __future__ import annotations

import subprocess
from typing import Callable

from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.models.hardware import HardwareProbeError, probe_nvidia_vram


FakeRunner = Callable[..., subprocess.CompletedProcess[str]]


def _runner_for(
    stdout: str, *, returncode: int = 0
) -> tuple[FakeRunner, list[tuple[list[str], dict[str, object]]]]:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def _runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((list(argv), dict(kwargs)))
        return subprocess.CompletedProcess(
            argv,
            returncode,
            stdout=stdout,
            stderr="synthetic diagnostic that must not be surfaced",
        )

    return _runner, calls


def _single_row_is_bound_to_requested_device_case() -> EvalOutcome:
    failures: list[str] = []
    runner, calls = _runner_for("\n6144, 3072\n\n")

    try:
        snapshot = probe_nvidia_vram(device_index=3, timeout_s=1.25, runner=runner)
    except Exception as exc:  # pragma: no cover - failure is reported as eval output
        failures.append(f"single-row probe unexpectedly failed: {type(exc).__name__}")
    else:
        if snapshot.total_mib != 6144 or snapshot.free_mib != 3072:
            failures.append(
                f"unexpected snapshot values: total={snapshot.total_mib}, free={snapshot.free_mib}"
            )
        if snapshot.device_index != 3:
            failures.append(
                f"requested device index was not preserved: {snapshot.device_index}"
            )

    if len(calls) != 1:
        failures.append(f"expected exactly one local probe call, got {len(calls)}")
    else:
        argv, kwargs = calls[0]
        if "--id=3" not in argv:
            failures.append("probe command did not bind the observation to device index 3")
        if "--query-gpu=memory.total,memory.free" not in argv:
            failures.append("probe command did not request only total/free VRAM counters")
        if kwargs.get("timeout") != 1.25:
            failures.append("probe did not preserve the bounded timeout")
        if kwargs.get("check") is not False:
            failures.append("probe runner invocation unexpectedly changed check semantics")
        if kwargs.get("stdin") is not subprocess.DEVNULL:
            failures.append("probe unexpectedly inherited stdin")

    return EvalOutcome(
        case_name="vram_probe_single_row_binds_requested_device",
        passed=not failures,
        detail="one non-empty nvidia-smi row must map to exactly the requested device",
        failures=tuple(failures),
    )


def _multi_row_output_fails_closed_case() -> EvalOutcome:
    failures: list[str] = []
    runner, calls = _runner_for("6144, 4096\n24576, 22000\n")

    try:
        probe_nvidia_vram(device_index=0, runner=runner)
    except HardwareProbeError as exc:
        message = str(exc)
        if message != "local NVIDIA VRAM probe returned ambiguous data":
            failures.append(f"unexpected fail-closed reason: {message!r}")
        for sensitive in ("6144", "4096", "24576", "22000", "synthetic diagnostic"):
            if sensitive in message:
                failures.append("ambiguous probe failure leaked raw hardware diagnostics")
                break
    except Exception as exc:  # pragma: no cover - failure is reported as eval output
        failures.append(f"ambiguous probe raised wrong exception: {type(exc).__name__}")
    else:
        failures.append("ambiguous multi-row probe was accepted instead of failing closed")

    if len(calls) != 1:
        failures.append(f"expected exactly one local probe call, got {len(calls)}")

    return EvalOutcome(
        case_name="vram_probe_multi_row_fails_closed",
        passed=not failures,
        detail="ambiguous nvidia-smi evidence must never be selected for local-model routing",
        failures=tuple(failures),
    )


def run_vram_probe_integrity_suite() -> list[EvalOutcome]:
    """Run the offline hardware-observation release regressions."""

    return [
        _single_row_is_bound_to_requested_device_case(),
        _multi_row_output_fails_closed_case(),
    ]
