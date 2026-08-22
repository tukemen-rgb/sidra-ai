"""Secret-safe local audit events for the private SIDRA API.

The audit boundary intentionally accepts metadata only. Raw operator queries,
model output, authorization headers, tokens, retrieved content, and gate finding
evidence are not fields on :class:`ApiAuditEvent`, so callers cannot
accidentally persist them through this interface.
"""

from __future__ import annotations

import json
import os
import stat
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sidra_ai.security.detectors import PIIDetector, SecretDetector


_SECRET_DETECTOR = SecretDetector()
_PII_DETECTOR = PIIDetector()
_REDACTED_REPOSITORY = "<redacted-repository>"


@dataclass(frozen=True)
class ApiAuditEvent:
    """One metadata-only API audit event.

    ``input_chars`` records only the length of operator input. Citation
    provenance is reduced to repository names; repository identifiers that
    match the secret/PII detectors are replaced with a constant placeholder.
    Paths, content, prompts and values detected by the security gate are
    deliberately excluded.
    """

    operation: str
    outcome: str
    decision: str
    input_chars: int
    repository_count: int
    citation_repositories: tuple[str, ...]
    model_invoked: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["citation_repositories"] = list(self.citation_repositories)
        return payload


@dataclass(frozen=True)
class AuditDurability:
    """How the audit sink has been doing, in counts.

    Audit writes are best-effort on purpose: a local disk fault must not turn
    a safe answer into an HTTP error. The cost of that choice is that a failed
    write is indistinguishable from an absent one, so an operator reading the
    log cannot tell "nothing happened" from "the record was lost". These
    counters are the missing half of that trade (SECURITY.md gap 2).

    ``last_failure_kind`` is an exception class name and nothing else. The
    message would carry the audit path, and this summary crosses an API
    boundary; a class name says whether the disk is full or the permissions
    are wrong, which is what an operator needs to act.
    """

    recorded: int = 0
    failed: int = 0
    last_failure_kind: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ApiAuditLog:
    """Append metadata-only events to a mode-0600 JSONL file.

    On platforms with ``dir_fd`` and ``O_NOFOLLOW`` support, every path
    component is opened relative to an already-open parent directory. This
    prevents an attacker from swapping a previously checked ancestor for a
    symlink between validation and the final append. Other platforms retain a
    fail-closed best-effort ancestry check.

    Each record is completed under a process-local lock. Short writes are
    retried until the full JSONL record is persisted, and zero-progress writes
    fail closed instead of leaving a silently truncated audit event. The file
    is forced to owner read/write permissions on every append.

    The log is local-only and does not perform network I/O.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._recorded = 0
        self._failed = 0
        self._last_failure_kind = ""

    @staticmethod
    def _repositories(values: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted({value for value in values if value}))

    @staticmethod
    def _audit_repository(value: str) -> str:
        """Return repository metadata safe enough for local persistence.

        Repository identifiers normally look like ``owner/name``, but this
        reducer must not assume every value reaching a response citation is
        canonical. Tainted provenance can otherwise turn the metadata-only
        audit sink into a secondary persistence path for a credential or PII.
        Any secret/PII detector hit therefore replaces the complete identifier
        with one context-free constant: no source text, length or fingerprint
        is retained.
        """

        if _SECRET_DETECTOR.detect(value).findings or _PII_DETECTOR.detect(value).findings:
            return _REDACTED_REPOSITORY
        return value

    @staticmethod
    def _audit_repositories(values: Iterable[str]) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    ApiAuditLog._audit_repository(value)
                    for value in values
                    if value
                }
            )
        )

    @staticmethod
    def _reject_parent_traversal(path: Path) -> None:
        if ".." in path.parts:
            raise OSError("refusing audit log path with parent traversal")

    @staticmethod
    def _supports_secure_dirfd() -> bool:
        supports_dir_fd = getattr(os, "supports_dir_fd", ())
        return (
            os.name != "nt"
            and hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
            and os.open in supports_dir_fd
            and os.mkdir in supports_dir_fd
        )

    @staticmethod
    def _path_components(path: Path) -> tuple[str, ...]:
        ApiAuditLog._reject_parent_traversal(path)
        parts = path.parts[1:] if path.is_absolute() else path.parts
        components = tuple(part for part in parts if part not in {"", "."})
        if not components:
            raise OSError("audit log path must name a file")
        return components

    @staticmethod
    def _directory_flags() -> int:
        return (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )

    @staticmethod
    def _open_child_directory(parent_fd: int, component: str) -> int:
        flags = ApiAuditLog._directory_flags()
        try:
            return os.open(component, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            try:
                os.mkdir(component, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                # A concurrent creator won the race. Re-open with O_NOFOLLOW;
                # a symlink or non-directory therefore still fails closed.
                pass
            return os.open(component, flags, dir_fd=parent_fd)

    @staticmethod
    def _open_regular_append_dirfd(path: Path) -> int:
        """Open an audit file by walking every parent through trusted dirfds."""

        components = ApiAuditLog._path_components(path)
        base = path.anchor if path.is_absolute() else "."
        parent_fd = os.open(base, ApiAuditLog._directory_flags())
        try:
            for component in components[:-1]:
                child_fd = ApiAuditLog._open_child_directory(parent_fd, component)
                os.close(parent_fd)
                parent_fd = child_fd

            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)

            fd = os.open(components[-1], flags, 0o600, dir_fd=parent_fd)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise OSError("audit log path is not a regular file")
                if hasattr(os, "fchmod"):
                    os.fchmod(fd, 0o600)
                return fd
            except Exception:
                os.close(fd)
                raise
        finally:
            os.close(parent_fd)

    @staticmethod
    def _assert_trusted_path_fallback(path: Path) -> None:
        """Best-effort ancestry check for platforms without secure dirfd walking."""

        ApiAuditLog._reject_parent_traversal(path)
        current = path
        while True:
            if current.is_symlink():
                raise OSError("refusing audit log through a symlinked path")
            parent = current.parent
            if parent == current:
                break
            current = parent

    @staticmethod
    def _open_regular_append_fallback(path: Path) -> int:
        ApiAuditLog._assert_trusted_path_fallback(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ApiAuditLog._assert_trusted_path_fallback(path)

        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)

        fd = os.open(path, flags, 0o600)
        try:
            ApiAuditLog._assert_trusted_path_fallback(path)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("audit log path is not a regular file")
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            elif os.chmod in os.supports_follow_symlinks:  # pragma: no cover
                os.chmod(path, 0o600, follow_symlinks=False)
            else:  # pragma: no cover - Windows: follow_symlinks unsupported;
                # the path was just re-verified symlink-free and the fd is a
                # regular file, so tightening by name cannot be redirected.
                os.chmod(path, 0o600)
            return fd
        except Exception:
            os.close(fd)
            raise

    @staticmethod
    def _open_regular_append(path: Path) -> int:
        if ApiAuditLog._supports_secure_dirfd():
            return ApiAuditLog._open_regular_append_dirfd(path)
        return ApiAuditLog._open_regular_append_fallback(path)

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        """Persist one complete record, retrying legal short writes."""

        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("audit log write made no progress")
            remaining = remaining[written:]

    def durability(self) -> AuditDurability:
        """Snapshot of write outcomes since this process started.

        Process-local by design: the counters answer "is the sink working
        now", and a persisted total would have to survive the very failure it
        is reporting on.
        """

        with self._lock:
            return AuditDurability(
                recorded=self._recorded,
                failed=self._failed,
                last_failure_kind=self._last_failure_kind,
            )

    def record(self, event: ApiAuditEvent) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event.to_dict(),
        }
        line = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )

        try:
            with self._lock:
                fd = self._open_regular_append(self.path)
                try:
                    self._write_all(fd, line)
                finally:
                    os.close(fd)
        except OSError as exc:
            # Counted here rather than at the call site: every caller reaches
            # the disk through this method, so a future one cannot forget to
            # report its own losses. The exception still propagates - whether
            # a lost record should fail the request stays the caller's call.
            with self._lock:
                self._failed += 1
                self._last_failure_kind = type(exc).__name__
            raise

        with self._lock:
            self._recorded += 1

    @staticmethod
    def _model_was_attempted(response: dict[str, object]) -> bool:
        """Return the non-sensitive model-attempt signal for an API result.

        Successful generation and OutputGuard refusal carry the public ``model``
        metadata block. A backend failure deliberately omits that block so model
        names/endpoints cannot leak, but its constant refusal reason still proves
        that generation was attempted. Audit history must not rewrite that failed
        attempt as "model not invoked".
        """

        if "model" in response:
            return True
        return bool(response.get("refused", False)) and response.get("reason") == (
            "model backend unavailable"
        )

    def record_response(
        self,
        *,
        operation: str,
        input_chars: int,
        requested_repositories: Iterable[str],
        response: dict[str, object],
    ) -> None:
        """Reduce an API response to non-sensitive audit metadata.

        Only explicitly selected keys are inspected. Security reasons,
        findings, model text, retrieved chunks and request content are never
        serialized. Citation repository identifiers are additionally screened
        for secret/PII shapes before persistence.

        ``github_analyze`` wraps the actual chat result under ``analysis``.
        Audit outcome, decision and citations must therefore be derived from
        that nested result when inference ran; otherwise an OutputGuard refusal
        could be recorded as ``allowed``/``unknown`` even though the API safely
        withheld the model output.
        """

        inference_skipped = bool(response.get("inference_skipped", False))
        audited_response = response
        analysis: dict[str, object] | None = None
        if operation == "github_analyze":
            raw_analysis = response.get("analysis")
            if isinstance(raw_analysis, dict):
                analysis = raw_analysis
                audited_response = raw_analysis

        security = audited_response.get("security")
        decision = "unknown"
        if isinstance(security, dict):
            raw_decision = security.get("decision")
            if isinstance(raw_decision, str):
                decision = raw_decision

        refused = bool(audited_response.get("refused", False))
        outcome = "refused" if refused else "skipped" if inference_skipped else "allowed"

        citations = audited_response.get("citations")
        citation_repositories: list[str] = []
        if isinstance(citations, list):
            for citation in citations:
                if isinstance(citation, dict):
                    repository = citation.get("repository")
                    if isinstance(repository, str):
                        citation_repositories.append(repository)

        results = audited_response.get("results")
        if isinstance(results, list):
            for result in results:
                if not isinstance(result, dict):
                    continue
                citation = result.get("citation")
                if isinstance(citation, dict):
                    repository = citation.get("repository")
                    if isinstance(repository, str):
                        citation_repositories.append(repository)

        model_invoked = False
        if operation == "chat":
            model_invoked = self._model_was_attempted(audited_response)
        elif operation == "github_analyze":
            model_invoked = analysis is not None and self._model_was_attempted(analysis)

        self.record(
            ApiAuditEvent(
                operation=operation,
                outcome=outcome,
                decision=decision,
                input_chars=max(0, input_chars),
                repository_count=len(self._repositories(requested_repositories)),
                citation_repositories=self._audit_repositories(citation_repositories),
                model_invoked=model_invoked,
            )
        )
