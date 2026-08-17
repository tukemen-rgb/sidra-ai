"""The security gate.

Everything entering SIDRA AI - repository content, operator messages, and
later web research - passes through :class:`SecurityGate`. The gate's job is
to *decide and record*, never to quietly discard:

* ``BLOCK``      content must not be indexed and must not reach the model.
* ``QUARANTINE`` content is retained only in a review-safe form, with reasons.
* ``ALLOW``      content may be indexed and placed in a DATA envelope.

Secrets are redacted from ``ALLOW`` content before it leaves the gate, so no
downstream component ever holds a credential in plaintext. Quarantine records
also never persist raw secret/PII-bearing content: quarantined material is
stored in its sanitized form, while blocked material is metadata-only.
"""

from __future__ import annotations

import json
import os
import stat
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from sidra_ai.config.settings import Settings, get_settings
from sidra_ai.documents import Document, Provenance
from sidra_ai.security.decisions import (
    Decision,
    Finding,
    FindingCategory,
    GateResult,
    Severity,
    strictest,
)
from sidra_ai.security.detectors import (
    OversizeDetector,
    PIIDetector,
    PromptInjectionDetector,
    SecretDetector,
    SourceAllowlistDetector,
)
from sidra_ai.security.redaction import redact_spans

#: Categories that always stop content from being indexed.
_BLOCKING_CATEGORIES = frozenset(
    {FindingCategory.UNPERMITTED_SOURCE, FindingCategory.OVERSIZED_INPUT}
)


@dataclass(frozen=True)
class GatePolicy:
    """Tunable thresholds. Defaults are the conservative v0.1 posture."""

    max_input_bytes: int = 512 * 1024
    quarantine_prompt_injection: bool = True
    """When ``True``, injection-flagged content stays out of the index."""

    redact_secrets: bool = True
    quarantine_secret_severity: Severity = Severity.CRITICAL
    """Findings at or above this severity quarantine even after redaction."""

    quarantine_pii_severity: Severity = Severity.MEDIUM
    """Medium+ PII candidates are redacted and quarantined by default."""

    @classmethod
    def from_settings(cls, settings: Settings) -> "GatePolicy":
        return cls(
            max_input_bytes=settings.max_input_bytes,
            quarantine_prompt_injection=settings.quarantine_prompt_injection,
        )


_SEVERITY_RANK = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


def _at_least(severity: Severity, threshold: Severity) -> bool:
    return _SEVERITY_RANK[severity] >= _SEVERITY_RANK[threshold]


class QuarantineStore:
    """Append-only audit record for content the gate refused to index.

    Security invariant: raw blocked/quarantined input is never persisted here.
    ``QUARANTINE`` records may retain the gate-sanitized content for human
    review. ``BLOCK`` records retain metadata only. No digest of the original
    content is stored either, because low-entropy PII can be guessable from an
    unkeyed hash.

    The quarantine file is local-only, must be a regular file, and is forced to
    owner-only permissions. Parent traversal, final-path symlinks, and any
    existing symlink in the parent ancestry are rejected before append/read.
    ``O_NOFOLLOW`` closes the final-component check/open race on platforms that
    provide it, preventing an attacker-controlled quarantine path from
    redirecting SIDRA's append/chmod operation onto another local file.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    @staticmethod
    def _assert_no_parent_traversal(path: Path) -> None:
        if ".." in path.parts:
            raise OSError("refusing quarantine store path with parent traversal")

    @staticmethod
    def _assert_no_symlink_ancestors(path: Path) -> None:
        """Reject any existing symlink in ``path`` or its ancestor chain."""

        current = path
        while True:
            if current.is_symlink():
                raise OSError(
                    "refusing quarantine store under a symlinked parent directory"
                )
            parent = current.parent
            if parent == current:
                return
            current = parent

    @classmethod
    def _prepare_parent(cls, path: Path) -> None:
        cls._assert_no_parent_traversal(path)
        cls._assert_no_symlink_ancestors(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        cls._assert_no_symlink_ancestors(path.parent)

    @classmethod
    def _open_regular_append(cls, path: Path) -> int:
        cls._prepare_parent(path)
        if path.is_symlink():
            raise OSError("refusing to write quarantine store through a symlink")

        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)

        fd = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("quarantine store path is not a regular file")
            cls._assert_no_symlink_ancestors(path.parent)
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            else:  # pragma: no cover - Windows fallback
                os.chmod(path, 0o600, follow_symlinks=False)
            return fd
        except Exception:
            os.close(fd)
            raise

    @classmethod
    def _open_regular_read(cls, path: Path) -> int:
        cls._assert_no_parent_traversal(path)
        cls._assert_no_symlink_ancestors(path.parent)
        if path.is_symlink():
            raise OSError("refusing to read quarantine store through a symlink")

        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)

        fd = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("quarantine store path is not a regular file")
            cls._assert_no_symlink_ancestors(path.parent)
            return fd
        except Exception:
            os.close(fd)
            raise

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("failed to append quarantine record")
            remaining = remaining[written:]

    def record(
        self,
        *,
        safe_content: str | None,
        original_length: int,
        provenance: Provenance | None,
        result: GateResult,
    ) -> None:
        entry: dict[str, Any] = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "provenance": provenance.to_dict() if provenance else None,
            "gate": result.to_dict(),
            "content": safe_content,
            "content_retention": "sanitized" if safe_content is not None else "metadata_only",
            "original_length": original_length,
        }
        line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")

        with self._lock:
            fd = self._open_regular_append(self.path)
            try:
                self._write_all(fd, line)
            finally:
                os.close(fd)

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            try:
                fd = self._open_regular_read(self.path)
            except FileNotFoundError:
                return []
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]


class SecurityGate:
    """Inspect content and decide whether it may enter the system."""

    def __init__(
        self,
        policy: GatePolicy | None = None,
        *,
        allowed_repositories: Sequence[str] | None = None,
        quarantine_store: QuarantineStore | None = None,
    ) -> None:
        settings = get_settings()
        self.policy = policy or GatePolicy.from_settings(settings)
        self.quarantine_store = quarantine_store
        self._secret = SecretDetector()
        self._pii = PIIDetector()
        self._injection = PromptInjectionDetector()
        self._oversize = OversizeDetector(self.policy.max_input_bytes)
        self._source = SourceAllowlistDetector(
            allowed_repositories
            if allowed_repositories is not None
            else settings.allowed_repositories
        )

    # ------------------------------------------------------------------
    def inspect(
        self,
        content: str,
        *,
        source: str = "operator",
        repository: str = "",
        provenance: Provenance | None = None,
    ) -> GateResult:
        """Run every detector and combine the verdicts.

        ``provenance`` is optional for direct operator calls. Document callers
        pass it so a quarantine event is recorded exactly once with source
        attribution, rather than first without provenance and then again.
        """

        findings: list[Finding] = []
        reasons: list[str] = []
        decision = Decision.ALLOW

        # GitHub is repository-scoped by policy. Treat missing repository
        # provenance as untrusted instead of letting an empty string bypass
        # the repository allowlist check in SourceAllowlistDetector.
        if source.strip().lower() == "github" and not repository.strip():
            findings.append(
                Finding(
                    category=FindingCategory.UNPERMITTED_SOURCE,
                    severity=Severity.CRITICAL,
                    detector="repository_required",
                    reason="GitHub input is missing required repository provenance",
                    metadata={"source": "github"},
                )
            )
            decision = Decision.BLOCK
            reasons.append("GitHub source is missing repository provenance")
            return self._finalize(
                content,
                content,
                findings,
                reasons,
                decision,
                redacted=False,
                provenance=provenance,
            )

        source_out = self._source.check(source=source, repository=repository)
        findings.extend(source_out.findings)
        if source_out.findings:
            decision = Decision.BLOCK
            reasons.append("source is not on the allowlist")
            # Do not inspect further: unpermitted content is not processed.
            # It is also not persisted verbatim in quarantine.
            return self._finalize(
                content,
                content,
                findings,
                reasons,
                decision,
                redacted=False,
                provenance=provenance,
            )

        oversize_out = self._oversize.detect(content)
        findings.extend(oversize_out.findings)
        if oversize_out.findings:
            decision = Decision.BLOCK
            reasons.append("input exceeds the byte budget")
            return self._finalize(
                content,
                content,
                findings,
                reasons,
                decision,
                redacted=False,
                provenance=provenance,
            )

        secret_out = self._secret.detect(content)
        pii_out = self._pii.detect(content)
        injection_out = self._injection.detect(content)
        findings.extend(secret_out.findings)
        findings.extend(pii_out.findings)
        findings.extend(injection_out.findings)

        spans = list(secret_out.spans)
        # Redact every PII finding at the policy's quarantine threshold. This
        # keeps medium-risk national-ID candidates out of the retrievable and
        # quarantine copies while still leaving low-risk role addresses usable.
        spans.extend(
            (f.start, f.end, f"pii_{f.detector}")
            for f in pii_out.findings
            if f.start >= 0
            and _at_least(f.severity, self.policy.quarantine_pii_severity)
        )

        sanitized = content
        redacted = False
        if self.policy.redact_secrets and spans:
            sanitized = redact_spans(content, spans)
            redacted = sanitized != content
            if redacted:
                reasons.append("credential/PII spans replaced with placeholders")

        if any(
            _at_least(f.severity, self.policy.quarantine_secret_severity)
            for f in secret_out.findings
        ):
            decision = strictest(decision, Decision.QUARANTINE)
            reasons.append(
                "high-confidence credential detected; redacted copy held for "
                "human review before indexing"
            )

        if any(
            _at_least(f.severity, self.policy.quarantine_pii_severity)
            for f in pii_out.findings
        ):
            decision = strictest(decision, Decision.QUARANTINE)
            reasons.append("personal information detected; held for human review")

        if injection_out.findings and self.policy.quarantine_prompt_injection:
            decision = strictest(decision, Decision.QUARANTINE)
            reasons.append(
                "prompt-injection patterns detected; content remains DATA and is "
                "held out of the index until reviewed"
            )
        elif injection_out.findings:
            reasons.append(
                "prompt-injection patterns detected; content is indexed as DATA "
                "inside a neutralizing envelope"
            )

        return self._finalize(
            content,
            sanitized,
            findings,
            reasons,
            decision,
            redacted=redacted,
            provenance=provenance,
        )

    # ------------------------------------------------------------------
    def _finalize(
        self,
        original: str,
        sanitized: str,
        findings: Sequence[Finding],
        reasons: Sequence[str],
        decision: Decision,
        *,
        redacted: bool,
        provenance: Provenance | None = None,
    ) -> GateResult:
        result = GateResult(
            decision=decision,
            findings=tuple(findings),
            content=sanitized,
            original_length=len(original),
            redacted=redacted,
            reasons=tuple(reasons),
        )
        if decision is not Decision.ALLOW and self.quarantine_store is not None:
            # QUARANTINE keeps only the sanitized review copy. BLOCK keeps no
            # content at all because source/size rejection may happen before
            # secret and PII detectors are allowed to inspect the payload.
            safe_content = sanitized if decision is Decision.QUARANTINE else None
            self.quarantine_store.record(
                safe_content=safe_content,
                original_length=len(original),
                provenance=provenance,
                result=result,
            )
        return result

    # ------------------------------------------------------------------
    def screen_document(self, document: Document) -> tuple[GateResult, Document | None]:
        """Inspect a document and return the version safe to index.

        Returns ``(result, document)`` where ``document`` is ``None`` unless
        the decision is ``ALLOW``. The returned document carries the redacted
        content and the finding labels, so provenance of the sanitization
        survives into the index.
        """

        result = self.inspect(
            document.content,
            source=document.provenance.source,
            repository=document.provenance.repository,
            provenance=document.provenance,
        )

        if result.decision is not Decision.ALLOW:
            return result, None

        screened = Document(
            content=result.content,
            provenance=document.provenance,
            redacted=result.redacted,
            security_findings=result.finding_labels,
        )
        return result, screened

    # ------------------------------------------------------------------
    def contains_secret(self, content: str) -> bool:
        """Cheap re-check used as defense in depth by the retrieval store."""

        return any(
            _at_least(f.severity, Severity.HIGH)
            for f in self._secret.detect(content).findings
        )
