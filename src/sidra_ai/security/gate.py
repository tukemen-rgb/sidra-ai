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

    On POSIX runtimes with secure ``dir_fd`` support, every parent component is
    opened relative to an already-open directory descriptor with
    ``O_NOFOLLOW``. The final JSONL is then opened relative to that verified
    parent. This closes the check/open race where a previously inspected
    ancestor could otherwise be swapped for a symlink before append or read.

    Platforms without that primitive retain a fail-closed best-effort ancestry
    check. The quarantine file is always required to be regular and is forced
    to owner-only permissions when the platform exposes ``fchmod``.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    @staticmethod
    def _reject_parent_traversal(path: Path) -> None:
        if ".." in path.parts:
            raise OSError("refusing quarantine store path with parent traversal")

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
        QuarantineStore._reject_parent_traversal(path)
        parts = path.parts[1:] if path.is_absolute() else path.parts
        components = tuple(part for part in parts if part not in {"", "."})
        if not components:
            raise OSError("quarantine store path must name a file")
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
    def _open_child_directory(parent_fd: int, component: str, *, create: bool) -> int:
        flags = QuarantineStore._directory_flags()
        try:
            return os.open(component, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            if not create:
                raise
            try:
                os.mkdir(component, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                # A concurrent creator won the race. Re-open with O_NOFOLLOW;
                # a symlink or non-directory therefore still fails closed.
                pass
            return os.open(component, flags, dir_fd=parent_fd)

    @classmethod
    def _open_parent_dirfd(cls, path: Path, *, create: bool) -> tuple[int, str]:
        components = cls._path_components(path)
        base = path.anchor if path.is_absolute() else "."
        parent_fd = os.open(base, cls._directory_flags())
        try:
            for component in components[:-1]:
                child_fd = cls._open_child_directory(
                    parent_fd,
                    component,
                    create=create,
                )
                os.close(parent_fd)
                parent_fd = child_fd
            return parent_fd, components[-1]
        except Exception:
            os.close(parent_fd)
            raise

    @classmethod
    def _open_regular_append_dirfd(cls, path: Path) -> int:
        parent_fd, filename = cls._open_parent_dirfd(path, create=True)
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(filename, flags, 0o600, dir_fd=parent_fd)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise OSError("quarantine store path is not a regular file")
                if hasattr(os, "fchmod"):
                    os.fchmod(fd, 0o600)
                return fd
            except Exception:
                os.close(fd)
                raise
        finally:
            os.close(parent_fd)

    @classmethod
    def _open_regular_read_dirfd(cls, path: Path) -> int:
        parent_fd, filename = cls._open_parent_dirfd(path, create=False)
        try:
            flags = os.O_RDONLY
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(filename, flags, dir_fd=parent_fd)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise OSError("quarantine store path is not a regular file")
                return fd
            except Exception:
                os.close(fd)
                raise
        finally:
            os.close(parent_fd)

    @staticmethod
    def _assert_trusted_path_fallback(path: Path) -> None:
        """Best-effort ancestry check without secure descriptor walking."""

        QuarantineStore._reject_parent_traversal(path)
        current = path
        while True:
            if current.is_symlink():
                raise OSError("refusing quarantine store through a symlinked path")
            parent = current.parent
            if parent == current:
                break
            current = parent

    @classmethod
    def _open_regular_append_fallback(cls, path: Path) -> int:
        cls._assert_trusted_path_fallback(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cls._assert_trusted_path_fallback(path)

        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            cls._assert_trusted_path_fallback(path)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("quarantine store path is not a regular file")
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            else:  # pragma: no cover - Windows fallback
                os.chmod(path, 0o600, follow_symlinks=False)
            return fd
        except Exception:
            os.close(fd)
            raise

    @classmethod
    def _open_regular_read_fallback(cls, path: Path) -> int:
        cls._assert_trusted_path_fallback(path)
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            cls._assert_trusted_path_fallback(path)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("quarantine store path is not a regular file")
            return fd
        except Exception:
            os.close(fd)
            raise

    @classmethod
    def _open_regular_append(cls, path: Path) -> int:
        if cls._supports_secure_dirfd():
            return cls._open_regular_append_dirfd(path)
        return cls._open_regular_append_fallback(path)

    @classmethod
    def _open_regular_read(cls, path: Path) -> int:
        if cls._supports_secure_dirfd():
            return cls._open_regular_read_dirfd(path)
        return cls._open_regular_read_fallback(path)

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("failed to append quarantine record")
            remaining = remaining[written:]

    @staticmethod
    def _audit_provenance(
        provenance: Provenance | None,
        result: GateResult,
    ) -> dict[str, Any] | None:
        """Return provenance safe to persist at the quarantine audit boundary.

        ``BLOCK`` may occur before secret/PII inspection for source rejection
        or oversized input, so all raw string provenance is dropped there.

        ``QUARANTINE`` happens only after source/repository allowlist checks,
        but the remaining provenance fields (path, URL, author, license,
        commit, and ``extra``) are still attacker-controlled and are not passed
        through the content secret/PII detectors. Persist only the already
        allowlist-bound source/repository plus typed attribution and lengths for
        those remaining fields. This keeps a repository-level review anchor
        without creating a secondary secret/PII persistence channel or a
        low-entropy digest oracle.
        """

        if provenance is None:
            return None
        if result.decision is Decision.ALLOW:
            return provenance.to_dict()

        common = {
            "source_type": provenance.source_type.value,
            "trust_level": provenance.trust_level.value,
            "timestamp": provenance.timestamp.isoformat(),
            "retrieved_at": provenance.retrieved_at.isoformat(),
            "path_length": len(provenance.path),
            "commit_sha_length": len(provenance.commit_sha),
            "license_length": len(provenance.license),
            "url_length": len(provenance.url),
            "author_length": len(provenance.author),
            "extra_count": len(provenance.extra),
        }
        if result.decision is Decision.QUARANTINE:
            return {
                "source": provenance.source,
                "repository": provenance.repository,
                **common,
            }
        return {
            **common,
            "source_length": len(provenance.source),
            "repository_length": len(provenance.repository),
        }

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
            "provenance": self._audit_provenance(provenance, result),
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
