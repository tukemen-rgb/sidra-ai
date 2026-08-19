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
from typing import AbstractSet, Any, Callable, Sequence

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


def _rejected_by_source_allowlist(result: GateResult) -> bool:
    """Did the source/repository allowlist itself refuse this input?

    This is the one case where ``source`` and ``repository`` are the
    untrusted values rather than operator-configured ones, so it decides
    whether the audit record may name them. Deciding it from the findings
    rather than from the decision matters: an oversized ``BLOCK`` and an
    unpermitted-source ``BLOCK`` are the same decision but not the same
    disclosure, and only the second one is refused before any check on the
    values could have passed.

    ``inspect`` returns immediately on an allowlist rejection, so a result
    carrying this category never also carries a later detector's findings.
    """

    return any(
        finding.category is FindingCategory.UNPERMITTED_SOURCE
        for finding in result.findings
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

        The remaining provenance fields (path, URL, author, license, commit
        and ``extra``) are attacker-controlled and never pass through the
        content secret/PII detectors, so they are persisted only as lengths.
        That keeps the audit record from becoming a second place secrets can
        land, and from becoming a low-entropy digest oracle.

        ``source`` and ``repository`` are different: they are bound to the
        operator's own allowlist. Whether they can be persisted depends on
        whether the allowlist check *passed*, not on the decision:

        * A rejection by the allowlist itself is the one case where the
          repository is precisely the untrusted value, and it is refused
          before any detector runs. Everything stays a length there.
        * Every other outcome - ``QUARANTINE``, or a ``BLOCK`` for size -
          has already cleared the allowlist, so the value is one of the
          operator's configured entries and naming it discloses nothing the
          operator did not write.

        Until this distinction existed, an oversized ``BLOCK`` was recorded
        anonymously: the durable log said something was refused for size and
        gave its byte count, but not where it came from. The ingestion report
        names the repository, but it is the response to one API call and is
        not persisted, so after the fact nobody could act on the rejection.
        Gap 6 of ``docs/SECURITY.md`` explains what stays dropped and why.
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
        if _rejected_by_source_allowlist(result):
            return {
                **common,
                "source_length": len(provenance.source),
                "repository_length": len(provenance.repository),
            }
        return {
            "source": provenance.source,
            "repository": provenance.repository,
            **common,
        }

    def record(
        self,
        *,
        safe_content: str | None,
        original_length: int,
        provenance: Provenance | None,
        result: GateResult,
        document_id: str | None = None,
    ) -> None:
        """Append one audit record.

        ``document_id`` is the only field here that can survive a release and
        be acted on later. Everything identifying - path, URL, author - is
        deliberately dropped by :meth:`_audit_provenance` because it is
        attacker-controlled and never passed through the detectors, which
        means a released entry cannot be rebuilt into a document from this
        log at all.

        The id closes that gap without reopening the one it was closing: it
        is a hash over repository, path and content, so it reveals none of
        them, and it is recomputable at the next ingestion. A release can
        therefore be keyed to it and applied when the same document comes
        back through the gate. The commit is deliberately not part of it -
        see :meth:`Document.doc_id` for why including it expired approvals
        on edits to unrelated files.
        """

        entry: dict[str, Any] = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "document_id": document_id,
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
        released_document_ids: Callable[[], AbstractSet[str]] | None = None,
    ) -> None:
        settings = get_settings()
        self.policy = policy or GatePolicy.from_settings(settings)
        self.quarantine_store = quarantine_store
        #: Optional source of human-approved document ids. Consulted only
        #: for QUARANTINE; see :meth:`_is_released`.
        self._released_document_ids = released_document_ids
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
        document_id: str | None = None,
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
                document_id=document_id,
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
                document_id=document_id,
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
                document_id=document_id,
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
                document_id=document_id,
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
        document_id: str | None = None,
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
                document_id=document_id,
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
            document_id=document.doc_id,
        )

        if result.decision is Decision.QUARANTINE and self._is_released(document.doc_id):
            # A human reviewed this exact document and approved it. The
            # findings stay on the record - the approval says "I looked at
            # these and accepted them", not "there was nothing to see".
            result = GateResult(
                decision=Decision.ALLOW,
                findings=result.findings,
                content=result.content,
                original_length=result.original_length,
                redacted=result.redacted,
                reasons=result.reasons
                + (
                    "released by human review; quarantine findings retained on "
                    "the record",
                ),
            )
        elif result.decision is not Decision.ALLOW:
            return result, None

        screened = Document(
            content=result.content,
            provenance=document.provenance,
            redacted=result.redacted,
            security_findings=result.finding_labels,
        )
        return result, screened

    # ------------------------------------------------------------------
    def _is_released(self, document_id: str) -> bool:
        """Has a human approved this exact document?

        Only ``QUARANTINE`` consults this. A ``BLOCK`` is a policy refusal -
        an unpermitted source, an oversized payload - and no amount of human
        approval turns a boundary into a suggestion.
        """

        if self._released_document_ids is None:
            return False
        try:
            released = self._released_document_ids()
        except Exception:  # noqa: BLE001 - a broken registry must not admit
            return False
        return document_id in released

    def contains_secret(self, content: str) -> bool:
        """Cheap re-check used as defense in depth by the retrieval store."""

        return any(
            _at_least(f.severity, Severity.HIGH)
            for f in self._secret.detect(content).findings
        )
