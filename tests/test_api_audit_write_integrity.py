"""Regression coverage for complete local audit-record writes."""

from __future__ import annotations

import json
import os

import pytest

import sidra_ai.api.audit as audit_module
from sidra_ai.api.audit import ApiAuditEvent, ApiAuditLog


def _event() -> ApiAuditEvent:
    return ApiAuditEvent(
        operation="chat",
        outcome="allowed",
        decision="allow",
        input_chars=12,
        repository_count=1,
        citation_repositories=("tukemen-rgb/sidra-ai",),
        model_invoked=True,
    )


def test_audit_record_retries_short_writes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "audit.jsonl"
    real_write = os.write
    calls = 0

    def short_write(fd: int, data: bytes | bytearray | memoryview) -> int:
        nonlocal calls
        calls += 1
        view = memoryview(data)
        return real_write(fd, view[: min(7, len(view))])

    monkeypatch.setattr(audit_module.os, "write", short_write)

    ApiAuditLog(path).record(_event())

    assert calls > 1
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["operation"] == "chat"
    assert payload["citation_repositories"] == ["tukemen-rgb/sidra-ai"]
    assert payload["model_invoked"] is True


def test_audit_record_fails_if_write_makes_no_progress(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit_module.os, "write", lambda _fd, _data: 0)

    with pytest.raises(OSError, match="no progress"):
        ApiAuditLog(tmp_path / "audit.jsonl").record(_event())
