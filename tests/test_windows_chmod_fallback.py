"""The permission-tightening fallbacks must survive a Windows-shaped ``os``.

2026-08-22, first run on a real Windows machine: every authenticated endpoint
returned HTTP 500 while ``/health`` and direct service calls worked. The cause
was ``os.chmod(path, 0o600, follow_symlinks=False)`` in the Windows branches of
three fallback writers - on Windows ``os.chmod`` does not support
``follow_symlinks`` and raises ``NotImplementedError``, which is not an
``OSError`` and therefore sailed past every disk-failure handler.

These tests recreate that ``os`` shape on any platform: no ``fchmod``, and a
``chmod`` that raises exactly like Windows when ``follow_symlinks=False`` is
passed. Each fallback writer must still produce a usable descriptor.
"""

from __future__ import annotations

import os
import stat

import pytest

from sidra_ai.api.audit import ApiAuditLog
from sidra_ai.security.gate import QuarantineStore


@pytest.fixture
def windows_shaped_os(monkeypatch):
    """Remove fchmod and make chmod reject follow_symlinks, as Windows does."""

    real_chmod = os.chmod

    def windows_chmod(path, mode, *, follow_symlinks=True, **kwargs):
        if not follow_symlinks:
            raise NotImplementedError(
                "chmod: follow_symlinks unavailable on this platform"
            )
        return real_chmod(path, mode, **kwargs)

    monkeypatch.delattr(os, "fchmod", raising=False)
    monkeypatch.setattr(os, "chmod", windows_chmod)
    monkeypatch.setattr(os, "supports_follow_symlinks", set())
    return windows_chmod


def test_audit_fallback_append_opens_without_fchmod(tmp_path, windows_shaped_os):
    target = tmp_path / "audit" / "api_audit.jsonl"
    fd = ApiAuditLog._open_regular_append_fallback(target)
    try:
        assert stat.S_ISREG(os.fstat(fd).st_mode)
        os.write(fd, b"{}\n")
    finally:
        os.close(fd)
    assert target.read_bytes() == b"{}\n"


def test_audit_record_survives_windows_shaped_os(tmp_path, windows_shaped_os, monkeypatch):
    """The original failure: one audit write turned a 200 into a 500."""

    monkeypatch.setattr(ApiAuditLog, "_supports_secure_dirfd", staticmethod(lambda: False))
    log = ApiAuditLog(tmp_path / "api_audit.jsonl")
    log.record_response(
        operation="github_analyze",
        input_chars=0,
        requested_repositories=("tukemen-rgb/site",),
        response={"ingestion": {"changed": False}, "inference_skipped": True},
    )
    assert log.durability().recorded == 1


def test_quarantine_fallback_append_opens_without_fchmod(tmp_path, windows_shaped_os):
    target = tmp_path / "quarantine" / "quarantine.jsonl"
    fd = QuarantineStore._open_regular_append_fallback(target)
    try:
        assert stat.S_ISREG(os.fstat(fd).st_mode)
    finally:
        os.close(fd)
    assert target.exists()
