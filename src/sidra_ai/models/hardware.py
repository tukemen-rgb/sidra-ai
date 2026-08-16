"""Local accelerator-memory probes for safe model routing.

The routing policy in :mod:`sidra_ai.models.routing` deliberately stays pure and
vendor-independent.  This module is the optional local observation layer: it
can sample an NVIDIA device with the already-installed ``nvidia-smi`` command
and turn that snapshot into a :class:`HardwareBudget` without network access or
model startup.

A probe failure is never silently converted into a guessed "free VRAM" value.
Callers that require an observed budget must handle :class:`HardwareProbeError`
and fail closed; callers that intentionally accept the static configured budget
can simply skip this probe.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

from sidra_ai.models.routing import (
    HardwareBudget,
    LocalModelCandidate,
    RouteDecision,
    select_local_model,
)


class HardwareProbeError(RuntimeError):
    """Raised when a local accelerator-memory observation cannot be trusted."""


@dataclass(frozen=True)
class VramSnapshot:
    """One local device-memory snapshot in MiB."""

    total_mib: int
    free_mib: int
    device_index: int = 0
    source: str = "nvidia-smi"

    def __post_init__(self) -> None:
        if self.device_index < 0:
            raise ValueError("device_index cannot be negative")
        if self.total_mib <= 0:
            raise ValueError("total_mib must be positive")
        if self.free_mib < 0 or self.free_mib > self.total_mib:
            raise ValueError("free_mib must be between zero and total_mib")
        if not self.source:
            raise ValueError("source is required")

    def to_hardware_budget(self, *, reserve_vram_mib: int = 512) -> HardwareBudget:
        """Build the existing routing budget from this observed snapshot."""

        return HardwareBudget(
            vram_mib=self.total_mib,
            reserve_vram_mib=reserve_vram_mib,
            observed_free_vram_mib=self.free_mib,
        )


Runner = Callable[..., subprocess.CompletedProcess[str]]


def probe_nvidia_vram(
    device_index: int = 0,
    *,
    timeout_s: float = 2.0,
    runner: Runner = subprocess.run,
) -> VramSnapshot:
    """Observe total/free VRAM for one local NVIDIA device.

    The command is fixed, runs without a shell, has a short timeout, does not
    read stdin, and asks only for aggregate memory counters.  stderr is never
    copied into the raised exception so local paths or driver diagnostics do
    not become part of application logs by accident.

    The function intentionally raises on command absence, timeout, non-zero
    exit, or malformed output.  Routing code must not treat a failed probe as a
    trustworthy zero/maximum-free value.
    """

    if not isinstance(device_index, int) or isinstance(device_index, bool):
        raise ValueError("device_index must be an integer")
    if device_index < 0 or device_index > 63:
        raise ValueError("device_index must be between 0 and 63")
    if timeout_s <= 0 or timeout_s > 10:
        raise ValueError("timeout_s must be greater than 0 and at most 10 seconds")

    argv = [
        "nvidia-smi",
        f"--id={device_index}",
        "--query-gpu=memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = runner(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise HardwareProbeError("local NVIDIA VRAM probe unavailable") from exc

    if completed.returncode != 0:
        raise HardwareProbeError("local NVIDIA VRAM probe failed")

    line = next((item.strip() for item in completed.stdout.splitlines() if item.strip()), None)
    if line is None:
        raise HardwareProbeError("local NVIDIA VRAM probe returned no data")

    fields = [item.strip() for item in line.split(",")]
    if len(fields) != 2:
        raise HardwareProbeError("local NVIDIA VRAM probe returned malformed data")

    try:
        total_mib, free_mib = (int(item) for item in fields)
        return VramSnapshot(
            total_mib=total_mib,
            free_mib=free_mib,
            device_index=device_index,
        )
    except (TypeError, ValueError) as exc:
        raise HardwareProbeError("local NVIDIA VRAM probe returned malformed data") from exc


def select_local_model_with_nvidia_probe(
    candidates: Sequence[LocalModelCandidate],
    *,
    planned_context_tokens: int,
    device_index: int = 0,
    reserve_vram_mib: int = 512,
    timeout_s: float = 2.0,
    runner: Runner = subprocess.run,
) -> RouteDecision:
    """Route against one freshly observed NVIDIA VRAM snapshot.

    This bridges the local hardware observation layer to the pure routing
    policy without starting a model process.  A failed or malformed probe is
    deliberately propagated as :class:`HardwareProbeError`; the helper never
    falls back to the static 6 GiB budget because doing so could admit a model
    that only fits when the GPU is otherwise idle.
    """

    snapshot = probe_nvidia_vram(
        device_index,
        timeout_s=timeout_s,
        runner=runner,
    )
    return select_local_model(
        candidates,
        hardware=snapshot.to_hardware_budget(reserve_vram_mib=reserve_vram_mib),
        planned_context_tokens=planned_context_tokens,
    )
