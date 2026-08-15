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

import base64
import binascii
import re
import unicodedata
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

# Unicode format/bidi controls can split a credential or personal identifier
# into visually recoverable fragments while evading ASCII-oriented detectors.
# Strip them only in the detector copy; never mutate text that is returned when
# the output is safe.
_INVISIBLE_OR_BIDI = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")

# A model can exfiltrate a credential without printing its literal shape by
# returning a reversible base64/base64url representation. Only bounded,
# token-like candidates are decoded, and decoded content is never retained.
_BASE64_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9+/_\-=])[A-Za-z0-9+/_\-]{16,8192}={0,2}(?![A-Za-z0-9+/_\-=])"
)
_MAX_DECODED_BYTES = 4096
_MAX_DECODE_CANDIDATES = 32


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

    Before matching, a detector-only copy is Unicode NFKC-normalized and has
    zero-width/bidi format controls removed. This prevents fullwidth or hidden-
    character obfuscation from bypassing provider-token and PII patterns while
    preserving the original safe output byte-for-byte when no finding exists.

    The guard also performs one bounded decode pass over base64/base64url-like
    output tokens. This catches reversible exfiltration such as a credential or
    personal email wrapped in base64 without turning arbitrary model output
    into an unbounded decoding workload. Decoded values are inspected in
    memory only and are never included in the result, logs, or exceptions.

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

    @staticmethod
    def _normalize_for_detection(content: str) -> str:
        normalized = unicodedata.normalize("NFKC", content)
        return _INVISIBLE_OR_BIDI.sub("", normalized)

    @staticmethod
    def _decoded_detection_variants(content: str) -> tuple[str, ...]:
        """Return bounded textual base64/base64url decodes for detector use.

        Invalid, binary, oversized, or empty candidates are ignored. At most
        ``_MAX_DECODE_CANDIDATES`` are inspected so crafted model output cannot
        turn the guard into an unbounded decoder. Decoded strings are
        intentionally ephemeral and never leave ``scan``.
        """

        decoded: list[str] = []
        for match in _BASE64_CANDIDATE.finditer(content):
            if len(decoded) >= _MAX_DECODE_CANDIDATES:
                break
            candidate = match.group()
            padded = candidate + "=" * (-len(candidate) % 4)
            try:
                raw = base64.b64decode(padded, altchars=b"-_", validate=True)
            except (binascii.Error, ValueError):
                continue
            if not raw or len(raw) > _MAX_DECODED_BYTES:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            decoded.append(OutputGuard._normalize_for_detection(text))
        return tuple(decoded)

    def _scan_text(self, content: str) -> tuple[Finding, ...]:
        secret_findings = self._blocking(self._secret.detect(content).findings)
        pii_findings = self._blocking(self._pii.detect(content).findings)
        return secret_findings + pii_findings

    def scan(self, content: str) -> OutputGuardResult:
        try:
            detector_content = self._normalize_for_detection(content)
            findings = list(self._scan_text(detector_content))
            for decoded_content in self._decoded_detection_variants(detector_content):
                findings.extend(self._scan_text(decoded_content))
        except Exception:
            return OutputGuardResult(
                blocked=True,
                content=_SAFE_BLOCK_MESSAGE,
                reason="output security detector failed closed",
            )

        if not findings:
            return OutputGuardResult(blocked=False, content=content)

        labels = tuple(sorted({finding.detector for finding in findings}))
        return OutputGuardResult(
            blocked=True,
            content=_SAFE_BLOCK_MESSAGE,
            finding_labels=labels,
            reason="high-confidence secret or PII detected in model output",
        )
