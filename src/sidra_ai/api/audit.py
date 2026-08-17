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


@dataclass(frozen=True)
class ApiAuditEvent:
    """One metadata-only API audit event.

    ``input_chars`` records only the length of operator input. Citation
    provenance is reduced to repository names; paths, content, prompts and
    values detected by the security gate are deliberately excluded.
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


class ApiAuditLog:
    """Append metadata-only events to a mode-0600 JSONL file.

    Each record is written with one ``os.write`` under a process-local lock and
    the file is forced to owner read/write permissions on every append. Explicit
    parent traversal and symlinks anywhere in the existing audit-path ancestry
    are rejected. The final path is also opened with ``O_NOFOLLOW`` when the
    platform provides it and verified as a regular file before data is written.

    The log is local-only and does not perform network I/O.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    @staticmethod
    def _repositories(values: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted({value for value in values if value}))

    @staticmethod
    def _assert_trusted_path(path: Path) -> None:
        """Reject explicit traversal or a symlink in any existing path component."""

        if ".." in path.parts:
            raise OSError("refusing audit log path with parent traversal")

        current = path
        while True:
            try:
                if current.is_symlink():
                    raise OSError("refusing audit log through a symlinked path")
            except OSError:
                raise

            parent = current.parent
            if parent == current:
                return
            current = parent

    @staticmethod
    def _open_regular_append(path: Path) -> int:
        """Open ``path`` for append without trusting redirected path components.

        Every existing path component is checked before directory creation and
        again afterwards. ``O_NOFOLLOW`` closes the final-component check/open
        race on platforms that expose it (including the Linux CI/runtime target),
        while ``fstat`` ensures a FIFO/device is never accepted as the audit log.
        """

        ApiAuditLog._assert_trusted_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ApiAuditLog._assert_trusted_path(path)

        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)

        fd = os.open(path, flags, 0o600)
        try:
            ApiAuditLog._assert_trusted_path(path)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("audit log path is not a regular file")
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            else:  # pragma: no cover - Windows fallback
                os.chmod(path, 0o600, follow_symlinks=False)
            return fd
        except Exception:
            os.close(fd)
            raise

    def record(self, event: ApiAuditEvent) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event.to_dict(),
        }
        line = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )

        with self._lock:
            fd = self._open_regular_append(self.path)
            try:
                os.write(fd, line)
            finally:
                os.close(fd)

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
        serialized.

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
                citation_repositories=self._repositories(citation_repositories),
                model_invoked=model_invoked,
            )
        )
