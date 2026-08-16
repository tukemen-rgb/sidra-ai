"""Offline release-gate checks for the Security quarantine filesystem boundary."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.security.decisions import Decision, GateResult
from sidra_ai.security.gate import QuarantineStore


def _result() -> GateResult:
    return GateResult(
        decision=Decision.QUARANTINE,
        findings=(),
        content="[REDACTED:test]",
        original_length=12,
        redacted=True,
        reasons=("synthetic release-gate record",),
    )


def _record(store: QuarantineStore) -> None:
    store.record(
        safe_content="[REDACTED:test]",
        original_length=12,
        provenance=None,
        result=_result(),
    )


def _symlink_available(root: Path) -> bool:
    target = root / "symlink-probe-target"
    link = root / "symlink-probe-link"
    target.write_text("probe", encoding="utf-8")
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError):
        return False
    return link.is_symlink()


def run_quarantine_path_safety_suite() -> tuple[EvalOutcome, ...]:
    """Require quarantine reads/writes to stay on regular owner-only local files."""

    failures: list[str] = []
    detail = "regular-file, final-symlink, and parent-symlink boundaries checked"

    with tempfile.TemporaryDirectory(prefix="sidra-quarantine-eval-") as tmp:
        root = Path(tmp)
        normal = root / "quarantine.jsonl"
        store = QuarantineStore(normal)
        _record(store)

        if not normal.is_file() or normal.is_symlink():
            failures.append("normal quarantine target was not a regular file")
        elif os.name != "nt" and stat.S_IMODE(normal.stat().st_mode) != 0o600:
            failures.append("normal quarantine target was not mode 0600")

        try:
            entries = store.entries()
        except OSError as exc:
            failures.append(f"normal quarantine file could not be read: {type(exc).__name__}")
        else:
            if len(entries) != 1 or entries[0].get("content") != "[REDACTED:test]":
                failures.append("normal quarantine record lost sanitized review content")

        if _symlink_available(root):
            target = root / "protected-target.txt"
            target.write_text("keep-me", encoding="utf-8")
            if os.name != "nt":
                target.chmod(0o644)
            before_mode = stat.S_IMODE(target.stat().st_mode)

            final_link = root / "redirected-quarantine.jsonl"
            final_link.symlink_to(target)
            linked_store = QuarantineStore(final_link)
            try:
                _record(linked_store)
            except OSError:
                pass
            else:
                failures.append("quarantine append followed a final symlink")

            if target.read_text(encoding="utf-8") != "keep-me":
                failures.append("final symlink target content was modified")
            if stat.S_IMODE(target.stat().st_mode) != before_mode:
                failures.append("final symlink target permissions were modified")

            try:
                linked_store.entries()
            except OSError:
                pass
            else:
                failures.append("quarantine read followed a final symlink")

            real_dir = root / "real-quarantine-dir"
            real_dir.mkdir()
            linked_dir = root / "linked-quarantine-dir"
            try:
                linked_dir.symlink_to(real_dir, target_is_directory=True)
            except (NotImplementedError, OSError):
                detail = "regular-file and final-symlink boundaries checked; directory symlink unavailable"
            else:
                try:
                    _record(QuarantineStore(linked_dir / "quarantine.jsonl"))
                except OSError:
                    pass
                else:
                    failures.append("quarantine append traversed a symlinked parent directory")
                if (real_dir / "quarantine.jsonl").exists():
                    failures.append("symlinked parent created a quarantine file behind the link")
        else:
            detail = "regular-file boundary checked; symlink creation unavailable"

    return (
        EvalOutcome(
            case_name="security_quarantine_path_filesystem_boundary",
            passed=not failures,
            detail=detail,
            failures=tuple(failures),
        ),
    )
