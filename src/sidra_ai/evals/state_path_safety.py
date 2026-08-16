"""Offline release-gate checks for the persisted ingestion cursor boundary."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.ingestion.state import StateStore, StateStoreError


_REPOSITORY = "tukemen-rgb/site"


def _symlink_available(root: Path) -> bool:
    target = root / "symlink-probe-target"
    link = root / "symlink-probe-link"
    target.write_text("probe", encoding="utf-8")
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError):
        return False
    return link.is_symlink()


def _mark(store: StateStore, sha: str) -> None:
    store.mark_ingested(
        _REPOSITORY,
        commit_sha=sha,
        document_count=1,
    )


def run_state_path_safety_suite() -> tuple[EvalOutcome, ...]:
    """Require ingestion cursors to fail closed on redirected/corrupt local state."""

    failures: list[str] = []
    detail = "cursor persistence, corruption, and symlink boundaries checked"

    with tempfile.TemporaryDirectory(prefix="sidra-state-eval-") as tmp:
        root = Path(tmp)

        normal = root / "state.json"
        store = StateStore(normal)
        _mark(store, "a" * 40)
        loaded = store.load().get(_REPOSITORY)
        if loaded.last_commit_sha != "a" * 40:
            failures.append("normal state round-trip lost the repository commit cursor")
        if os.name != "nt" and stat.S_IMODE(normal.stat().st_mode) != 0o600:
            failures.append("normal state target was not mode 0600")

        corrupt = root / "corrupt-state.json"
        original_corrupt = "{not-valid-json\n"
        corrupt.write_text(original_corrupt, encoding="utf-8")
        try:
            _mark(StateStore(corrupt), "b" * 40)
        except StateStoreError:
            pass
        else:
            failures.append("corrupt persisted cursor was silently reset/overwritten")
        if corrupt.read_text(encoding="utf-8") != original_corrupt:
            failures.append("corrupt persisted cursor changed after failed update")

        if _symlink_available(root):
            protected = root / "protected-state.json"
            protected_payload = json.dumps({"version": 1, "repositories": {}}) + "\n"
            protected.write_text(protected_payload, encoding="utf-8")
            if os.name != "nt":
                protected.chmod(0o644)
            before_mode = stat.S_IMODE(protected.stat().st_mode)

            final_link = root / "redirected-state.json"
            final_link.symlink_to(protected)
            redirected = StateStore(final_link)
            try:
                redirected.load()
            except StateStoreError:
                pass
            else:
                failures.append("state read followed a final symlink")
            try:
                _mark(redirected, "c" * 40)
            except StateStoreError:
                pass
            else:
                failures.append("state update followed a final symlink")

            if protected.read_text(encoding="utf-8") != protected_payload:
                failures.append("final symlink target content was modified")
            if stat.S_IMODE(protected.stat().st_mode) != before_mode:
                failures.append("final symlink target permissions were modified")

            real_root = root / "real-state-root"
            real_root.mkdir()
            linked_root = root / "linked-state-root"
            try:
                linked_root.symlink_to(real_root, target_is_directory=True)
            except (NotImplementedError, OSError):
                detail = "cursor/corruption/final-symlink checked; directory symlink unavailable"
            else:
                ancestor_store = StateStore(linked_root / "nested" / "state.json")
                try:
                    _mark(ancestor_store, "d" * 40)
                except StateStoreError:
                    pass
                else:
                    failures.append("state update traversed a symlinked parent ancestry")
                if (real_root / "nested").exists():
                    failures.append("symlinked ancestry created state data behind the link")
        else:
            detail = "cursor persistence/corruption checked; symlink creation unavailable"

    return (
        EvalOutcome(
            case_name="ingestion_state_cursor_filesystem_boundary",
            passed=not failures,
            detail=detail,
            failures=tuple(failures),
        ),
    )
