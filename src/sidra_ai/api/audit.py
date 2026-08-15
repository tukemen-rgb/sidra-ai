"""Secret-safe local audit events for the private SIDRA API.

The audit boundary intentionally accepts metadata only. Raw operator queries,
model output, authorization headers, tokens, retrieved content, and gate finding
evidence are not fields on :class:`ApiAuditEvent`, so callers cannot
accidentally persist them through this interface.
"""

from __future__ import annotations

import json
import os
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
    the file is forced to owner read/write permissions on every append. The
    log is local-only and does not perform network I/O.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    @staticmethod
    def _repositories(values: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted({value for value in values if value}))

    def record(self, event: ApiAuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event.to_dict(),
        }
        line = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )

        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        with self._lock:
            fd = os.open(self.path, flags, 0o600)
            try:
                os.chmod(self.path, 0o600)
                os.write(fd, line)
            finally:
                os.close(fd)

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
        """

        security = response.get("security")
        decision = "unknown"
        if isinstance(security, dict):
            raw_decision = security.get("decision")
            if isinstance(raw_decision, str):
                decision = raw_decision

        refused = bool(response.get("refused", False))
        inference_skipped = bool(response.get("inference_skipped", False))
        outcome = "refused" if refused else "skipped" if inference_skipped else "allowed"

        citations = response.get("citations")
        citation_repositories: list[str] = []
        if isinstance(citations, list):
            for citation in citations:
                if isinstance(citation, dict):
                    repository = citation.get("repository")
                    if isinstance(repository, str):
                        citation_repositories.append(repository)

        results = response.get("results")
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
            # A model may have run even when OutputGuard withholds its answer.
            # Presence of the model metadata is the non-sensitive invocation
            # signal; refusal alone must not rewrite history to "not invoked".
            model_invoked = "model" in response
        elif operation == "github_analyze":
            analysis = response.get("analysis")
            model_invoked = isinstance(analysis, dict) and "model" in analysis

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
