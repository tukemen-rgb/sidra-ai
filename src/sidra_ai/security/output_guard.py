"""Fail-closed screening for text produced by local model backends.

The ingestion security gate keeps secrets/PII out of RAG, but model output is a
separate trust boundary. A local model can still echo operator-provided values
or generate credential-shaped material. This module provides the L2-owned
screening primitive that the API lane can call immediately before returning a
model answer.

The guard deliberately does not persist or log model output. If a high-
confidence secret or personal-information finding is detected, the entire
answer is replaced with a constant safe message rather than partially
redacting and accidentally leaking surrounding sensitive context.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.security.decisions import Finding, Severity
from sidra_ai.security.detectors import PIIDetector, SecretDetector


_SEVERITY_RANK = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}

_SAFE_BLOCK_MESSAGE = (
    "Response withheld because the output security check detected potentially "
    "sensitive information."
)


@dataclass(frozen=True)
class OutputGuardResult:
    """Safe-to-return result from :class:`OutputGuard`.

    ``content`` never contains the original model output when ``blocked`` is
    true. Only detector labels are retained so callers can audit the category
    without storing the sensitive value itself.
    """

    blocked: bool
    content: str
    finding_labels: tuple[str, ...] = ()
    reason: str | None = None


class OutputGuard:
    """Screen model output for secret/PII leakage before API return.

    High/critical secret or PII findings block the whole response. Lower
    severity findings remain non-blocking because role addresses and generic
    high-entropy strings otherwise create excessive false positives.

    Detector failures fail closed: returning an unchecked answer is less safe
    than returning a constant withholding message.
    """

    def __init__(self) -> None:
        self._secret = SecretDetector()
        self._pii = PIIDetector()

    @staticmethod
    def _blocking(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
        return tuple(
            finding
            for finding in findings
            if _SEVERITY_RANK[finding.severity] >= _SEVERITY_RANK[Severity.HIGH]
        )

    def scan(self, content: str) -> OutputGuardResult:
        try:
            secret_findings = self._blocking(self._secret.detect(content).findings)
            pii_findings = self._blocking(self._pii.detect(content).findings)
        except Exception:
            return OutputGuardResult(
                blocked=True,
                content=_SAFE_BLOCK_MESSAGE,
                reason="output security detector failed closed",
            )

        findings = secret_findings + pii_findings
        if not findings:
            return OutputGuardResult(blocked=False, content=content)

        labels = tuple(sorted({finding.detector for finding in findings}))
        return OutputGuardResult(
            blocked=True,
            content=_SAFE_BLOCK_MESSAGE,
            finding_labels=labels,
            reason="high-confidence secret or PII detected in model output",
        )
