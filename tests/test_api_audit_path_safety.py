"""Filesystem-safety regressions for the local API audit log."""

from __future__ import annotations

import json
import os
import stat

import pytest

from sidra_ai.api.audit import ApiAuditEvent, ApiAuditLog


def _event() -> ApiAuditEvent:
    return ApiAuditEvent(
        operation="chat",
        outcome="allowed",
        decision="allow",
        input_chars=5,
        repository_count=0,
        citation_repositories=(),
        model_invoked=True,
    )


def test_normal_audit_file_is_regular_owner_only_jsonl(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"

    ApiAuditLog(path).record(_event())

    assert path.is_file()
    assert not path.is_symlink()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["operation"] == "chat"
    assert payload["decision"] == "allow"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_audit_log_refuses_final_symlink_without_touching_target(tmp_path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("keep-me", encoding="utf-8")
    target.chmod(0o644)
    before_mode = stat.S_IMODE(target.stat().st_mode)

    link = tmp_path / "audit.jsonl"
    link.symlink_to(target)

    with pytest.raises(OSError):
        ApiAuditLog(link).record(_event())

    assert target.read_text(encoding="utf-8") == "keep-me"
    assert stat.S_IMODE(target.stat().st_mode) == before_mode


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_audit_log_refuses_symlinked_parent_directory(tmp_path) -> None:
    real_dir = tmp_path / "real-audit-dir"
    real_dir.mkdir()
    linked_dir = tmp_path / "audit-dir"
    linked_dir.symlink_to(real_dir, target_is_directory=True)

    with pytest.raises(OSError):
        ApiAuditLog(linked_dir / "audit.jsonl").record(_event())

    assert not (real_dir / "audit.jsonl").exists()
