from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence
from urllib.parse import urlsplit

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.decisions import Decision
from sidra_ai.security.detectors import SourceAllowlistDetector
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

from .broker import FetchBroker


class FetchIngestionError(RuntimeError):
    """Raised when a fetched response cannot safely cross into retrieval."""


@dataclass(frozen=True, slots=True)
class FetchIngestionResult:
    """Metadata-only result from one broker -> gate -> retrieval attempt."""

    decision: Decision
    provenance: Provenance
    document_id: str | None
    finding_labels: tuple[str, ...]
    redacted: bool


class _WebSecurityGate(SecurityGate):
    """Capability-scoped SecurityGate for broker-approved Web DATA only.

    The v0.1 SecurityGate intentionally defaults its source allowlist to GitHub and
    operator input. Web fetch is a separate capability, so this adapter narrows the
    gate to the exact pseudo-repositories derived from FetchPolicy.allowed_hosts
    instead of widening the process-wide default source policy.
    """

    def __init__(
        self,
        *,
        allowed_repositories: Sequence[str],
        policy: GatePolicy | None,
        quarantine_store: QuarantineStore | None,
    ) -> None:
        super().__init__(
            policy=policy,
            allowed_repositories=allowed_repositories,
            quarantine_store=quarantine_store,
        )
        # SecurityGate composes this detector internally. Keep the default gate
        # unchanged; only this Fetch capability accepts source="web".
        self._source = SourceAllowlistDetector(  # noqa: SLF001 - capability adapter
            allowed_repositories,
            allowed_sources=("web",),
        )


class WebIngestionBridge:
    """Convert one bounded FetchBroker response into ALLOW-only RAG DATA.

    This is intentionally a library boundary, not an API route. It performs no DNS,
    socket, redirect, or HTTP work itself: FetchBroker owns that boundary. Every final
    response is converted to SourceType.WEB / TrustLevel.EXTERNAL provenance, screened
    by a Web-only SecurityGate, and indexed only when the verdict is ALLOW.
    """

    def __init__(
        self,
        broker: FetchBroker,
        store: DocumentStore,
        *,
        gate_policy: GatePolicy | None = None,
        quarantine_store: QuarantineStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.broker = broker
        self.store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        web_repositories = tuple(
            f"web/{host}" for host in sorted(self.broker.policy.allowed_hosts)
        )
        self._gate = _WebSecurityGate(
            allowed_repositories=web_repositories,
            policy=gate_policy,
            quarantine_store=quarantine_store,
        )

    def ingest(self, url: str) -> FetchIngestionResult:
        response = self.broker.fetch(url)
        if response.status != 200 or response.content_type is None:
            raise FetchIngestionError("broker did not return a complete final response")

        canonical_url, host = self.broker.policy.canonicalize_url(response.url)
        if canonical_url != response.url:
            raise FetchIngestionError("broker response URL is not canonical")

        try:
            content = response.body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FetchIngestionError("fetched content is not valid UTF-8") from exc

        observed_at = self._observed_at()
        content_digest = hashlib.sha256(response.body).hexdigest()
        parsed = urlsplit(canonical_url)
        logical_path = parsed.path or "/"
        extra: dict[str, str] = {
            "source_host": host,
            "content_type": response.content_type,
            "content_sha256": content_digest,
            "connected_ip": response.connected_ip,
        }
        if parsed.query:
            query_digest = hashlib.sha256(parsed.query.encode("utf-8")).hexdigest()
            logical_path = f"{logical_path}?query_sha256={query_digest}"
            extra["query_sha256"] = query_digest

        provenance = Provenance(
            source="web",
            repository=f"web/{host}",
            path=logical_path,
            commit_sha=content_digest,
            timestamp=observed_at,
            source_type=SourceType.WEB,
            trust_level=TrustLevel.EXTERNAL,
            license="unknown",
            url=canonical_url,
            retrieved_at=observed_at,
            extra=extra,
        )
        document = Document(content=content, provenance=provenance)
        gate_result, screened = self._gate.screen_document(document)

        document_id: str | None = None
        if screened is not None:
            document_id = self.store.add(screened, gate_result=gate_result)

        return FetchIngestionResult(
            decision=gate_result.decision,
            provenance=provenance,
            document_id=document_id,
            finding_labels=gate_result.finding_labels,
            redacted=gate_result.redacted,
        )

    def _observed_at(self) -> datetime:
        observed = self._clock()
        if not isinstance(observed, datetime) or observed.tzinfo is None:
            raise FetchIngestionError("retrieval clock must return timezone-aware datetime")
        return observed.astimezone(timezone.utc)
