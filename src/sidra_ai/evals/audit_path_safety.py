"""Offline release-gate checks for the local API audit filesystem boundary."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from sidra_ai.api.audit import ApiAuditEvent, ApiAuditLog
from sidra_ai.evals.cases import EvalOutcome


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


def _symlink_available(root: Path) -> bool:
    """Return whether this runtime can create a file symlink for the eval."""

    target = root / "symlink-probe-target"
    link = root / "symlink-probe-link"
    target.write_text("probe", encoding="utf-8")
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError):
        return False
    return link.is_symlink()


def run_audit_path_safety_suite() -> tuple[EvalOutcome, ...]:
    """Require audit writes to stay on a regular owner-only local file."""

    failures: list[str] = []
    detail = "regular-file and symlink boundaries checked"

    with tempfile.TemporaryDirectory(prefix="sidra-audit-eval-") as tmp:
        root = Path(tmp)
        normal = root / "audit.jsonl"
        ApiAuditLog(normal).record(_event())

        if not normal.is_file() or normal.is_symlink():
            failures.append("normal audit target was not a regular file")
        elif os.name != "nt" and stat.S_IMODE(normal.stat().st_mode) != 0o600:
            failures.append("normal audit target was not mode 0600")

        try:
            payload = json.loads(normal.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"normal audit record was unreadable JSON: {type(exc).__name__}")
        else:
            if payload.get("operation") != "chat" or payload.get("decision") != "allow":
                failures.append("normal audit record lost expected metadata")

        if _symlink_available(root):
            target = root / "protected-target.txt"
            target.write_text("keep-me", encoding="utf-8")
            if os.name != "nt":
                target.chmod(0o644)
            before_mode = stat.S_IMODE(target.stat().st_mode)

            final_link = root / "redirected-audit.jsonl"
            final_link.symlink_to(target)
            try:
                ApiAuditLog(final_link).record(_event())
            except OSError:
                pass
            else:
                failures.append("audit append followed a final symlink")

            if target.read_text(encoding="utf-8") != "keep-me":
                failures.append("final symlink target content was modified")
            if stat.S_IMODE(target.stat().st_mode) != before_mode:
                failures.append("final symlink target permissions were modified")

            real_dir = root / "real-audit-dir"
            real_dir.mkdir()
            linked_dir = root / "linked-audit-dir"
            try:
                linked_dir.symlink_to(real_dir, target_is_directory=True)
            except (NotImplementedError, OSError):
                detail = "final symlink checked; directory symlink unavailable"
            else:
                try:
                    ApiAuditLog(linked_dir / "audit.jsonl").record(_event())
                except OSError:
                    pass
                else:
                    failures.append("audit append traversed a symlinked parent directory")
                if (real_dir / "audit.jsonl").exists():
                    failures.append("symlinked parent created an audit file behind the link")
        else:
            detail = "regular-file boundary checked; symlink creation unavailable"

    return (
        EvalOutcome(
            case_name="api_audit_path_filesystem_boundary",
            passed=not failures,
            detail=detail,
            failures=tuple(failures),
        ),
    )
