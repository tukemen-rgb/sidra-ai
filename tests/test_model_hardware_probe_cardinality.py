"""NVIDIA VRAM routing must use one unambiguous device observation."""

from __future__ import annotations

import subprocess

import pytest

from sidra_ai.models.hardware import HardwareProbeError, probe_nvidia_vram


def _completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["nvidia-smi"],
        returncode=0,
        stdout=stdout,
        stderr="",
    )


def test_probe_accepts_exactly_one_non_empty_row() -> None:
    snapshot = probe_nvidia_vram(
        0,
        runner=lambda *args, **kwargs: _completed("\n6144, 3072\n\n"),
    )

    assert snapshot.total_mib == 6144
    assert snapshot.free_mib == 3072
    assert snapshot.device_index == 0


def test_probe_rejects_ambiguous_multi_row_output() -> None:
    with pytest.raises(HardwareProbeError, match="ambiguous"):
        probe_nvidia_vram(
            0,
            runner=lambda *args, **kwargs: _completed(
                "6144, 3072\n8192, 7000\n"
            ),
        )
