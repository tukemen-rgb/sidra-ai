"""Fail-closed screening for text produced by local model backends.

The ingestion security gate keeps secrets/PII out of RAG, but model output is a
separate trust boundary. A local model can still echo operator-provided values
or generate credential-shaped material. This module provides the L2-owned
screening primitive that the API lane can call immediately before returning a
model answer.

The guard deliberately does not persist or log model output. If a secret-like
or high-confidence personal-information finding is detected, the entire answer
is replaced with a constant safe message rather than partially redacting and
accidentally leaking surrounding sensitive context.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote_to_bytes

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

# Percent-encoding is another reversible text-only exfiltration path that can
# hide a provider token or a single critical PII delimiter such as the '@' in
# an email address. Keep matching bounded and detector-only; do not rewrite
# safe output. A single valid %HH escape is enough to merit one decode pass.
_PERCENT_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9%._~\-])[A-Za-z0-9%._~\-]{4,8192}(?![A-Za-z0-9%._~\-])"
)
_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_MAX_PERCENT_CANDIDATES = 32

# Plain hexadecimal is also a reversible exfiltration form. Provider prefixes
# and email delimiters disappear completely after hex encoding, while the
# resulting 0-9/a-f alphabet often falls below the generic entropy threshold.
# Only contiguous, even-length byte strings are considered, and decoding is
# bounded exactly like the other detector-only variants.
_HEX_CANDIDATE = re.compile(
    r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){16,4096}(?![0-9A-Fa-f])"
)
_MAX_HEX_CANDIDATES = 32

# JSON/code-style escapes are a common model-output form and can hide the
# handful of ASCII delimiters that secret/PII detectors rely on. Decode only
# explicit \uXXXX and \xHH escapes into an ephemeral detector copy. If an
# answer contains an excessive number of escapes, fail closed rather than
# spending unbounded work on an adversarial payload.
_STRING_ESCAPE = re.compile(
    r"\\(?:u(?P<unicode>[0-9A-Fa-f]{4})|x(?P<byte>[0-9A-Fa-f]{2}))"
)
_MAX_STRING_ESCAPES = 4096

# Reversible encodings can be composed (for example base64(percent(secret))).
# The previous one-pass guard detected each encoding independently but did not
# inspect decoded output again. Walk a deliberately tiny bounded graph instead:
# two decode layers are enough to close the straightforward composition bypass
# without turning arbitrary model output into an unbounded decoder.
_MAX_DECODE_DEPTH = 2
_MAX_TOTAL_DECODED_VARIANTS = 64


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

    Secret findings at MEDIUM or above block the whole response. This is
    intentionally stricter than the ingestion path: output is an immediate
    exfiltration boundary, so an unprefixed high-entropy credential must not be
    returned merely because it lacks a provider-specific prefix. PII remains
    blocking at HIGH/CRITICAL so role addresses and other low-risk metadata do
    not make ordinary responses unusable.

    Before matching, a detector-only copy is Unicode NFKC-normalized and has
    zero-width/bidi format controls removed. This prevents fullwidth or hidden-
    character obfuscation from bypassing provider-token and PII patterns while
    preserving the original safe output byte-for-byte when no finding exists.

    The guard performs bounded decoding of base64/base64url-like,
    percent-encoded, hexadecimal, and JSON/code escaped output. Decoded variants
    are re-inspected for at most two layers, so composed reversible encodings
    cannot trivially hide a secret. Candidate and global variant budgets keep
    adversarial output from causing unbounded decoding work; exhausting any
    budget fails closed rather than silently skipping unchecked candidates.
    Decoded values remain ephemeral and never leave ``scan``.

    Detector failures fail closed: returning an unchecked answer is less safe
    than returning a constant withholding message.
    """

    def __init__(self) -> None:
        self._secret = SecretDetector()
        self._pii = PIIDetector()

    @staticmethod
    def _blocking(
        findings: tuple[Finding, ...], *, threshold: Severity = Severity.HIGH
    ) -> tuple[Finding, ...]:
        return tuple(
            finding
            for finding in findings
            if _SEVERITY_RANK[finding.severity] >= _SEVERITY_RANK[threshold]
        )

    @staticmethod
    def _normalize_for_detection(content: str) -> str:
        normalized = unicodedata.normalize("NFKC", content)
        return _INVISIBLE_OR_BIDI.sub("", normalized)

    @staticmethod
    def _decoded_detection_variants(content: str) -> tuple[str, ...]:
        """Return bounded textual base64/base64url decodes for detector use."""

        decoded: list[str] = []
        for match in _BASE64_CANDIDATE.finditer(content):
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
            if len(decoded) >= _MAX_DECODE_CANDIDATES:
                raise ValueError("base64 decode candidate budget exceeded")
            decoded.append(OutputGuard._normalize_for_detection(text))
        return tuple(decoded)

    @staticmethod
    def _percent_decoded_detection_variants(content: str) -> tuple[str, ...]:
        """Return bounded percent-decoded textual variants for detector use."""

        decoded: list[str] = []
        for match in _PERCENT_CANDIDATE.finditer(content):
            candidate = match.group()
            if _PERCENT_ESCAPE.search(candidate) is None:
                continue
            try:
                raw = unquote_to_bytes(candidate)
            except (TypeError, ValueError):
                continue
            if not raw or len(raw) > _MAX_DECODED_BYTES:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            normalized = OutputGuard._normalize_for_detection(text)
            if normalized == candidate:
                continue
            if len(decoded) >= _MAX_PERCENT_CANDIDATES:
                raise ValueError("percent decode candidate budget exceeded")
            decoded.append(normalized)
        return tuple(decoded)

    @staticmethod
    def _hex_decoded_detection_variants(content: str) -> tuple[str, ...]:
        """Return bounded textual hex decodes for detector use."""

        decoded: list[str] = []
        for match in _HEX_CANDIDATE.finditer(content):
            candidate = match.group()
            try:
                raw = bytes.fromhex(candidate)
            except ValueError:
                continue
            if not raw or len(raw) > _MAX_DECODED_BYTES:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            normalized = OutputGuard._normalize_for_detection(text)
            if normalized == candidate:
                continue
            if len(decoded) >= _MAX_HEX_CANDIDATES:
                raise ValueError("hex decode candidate budget exceeded")
            decoded.append(normalized)
        return tuple(decoded)

    @staticmethod
    def _escaped_detection_variants(content: str) -> tuple[str, ...]:
        """Return one bounded JSON/code-escape-decoded detector variant."""

        pieces: list[str] = []
        cursor = 0
        count = 0
        changed = False

        for match in _STRING_ESCAPE.finditer(content):
            count += 1
            if count > _MAX_STRING_ESCAPES:
                raise ValueError("too many reversible string escapes in model output")

            pieces.append(content[cursor : match.start()])
            unicode_hex = match.group("unicode")
            byte_hex = match.group("byte")
            codepoint = int(unicode_hex or byte_hex, 16)
            if unicode_hex is not None and 0xD800 <= codepoint <= 0xDFFF:
                pieces.append(match.group())
            else:
                pieces.append(chr(codepoint))
                changed = True
            cursor = match.end()

        if not changed:
            return ()

        pieces.append(content[cursor:])
        decoded = OutputGuard._normalize_for_detection("".join(pieces))
        if decoded == content:
            return ()
        return (decoded,)

    @classmethod
    def _reversible_detection_variants(cls, content: str) -> tuple[str, ...]:
        """Expand reversible encodings with strict depth and count budgets.

        Each decoded value is normalized, deduplicated, and may itself be
        decoded once more. The original detector copy is not returned because
        ``scan`` already checks it directly. If a new unique variant would
        exceed the global budget, raise so ``scan`` withholds the entire output
        instead of silently leaving later candidates unchecked.
        """

        decoders = (
            cls._decoded_detection_variants,
            cls._percent_decoded_detection_variants,
            cls._hex_decoded_detection_variants,
            cls._escaped_detection_variants,
        )
        seen = {content}
        frontier = [content]
        variants: list[str] = []

        for _ in range(_MAX_DECODE_DEPTH):
            next_frontier: list[str] = []
            for candidate in frontier:
                for decoder in decoders:
                    for decoded in decoder(candidate):
                        if decoded in seen:
                            continue
                        if len(variants) >= _MAX_TOTAL_DECODED_VARIANTS:
                            raise ValueError("reversible decode variant budget exceeded")
                        seen.add(decoded)
                        variants.append(decoded)
                        next_frontier.append(decoded)
            if not next_frontier:
                break
            frontier = next_frontier

        return tuple(variants)

    def _scan_text(self, content: str) -> tuple[Finding, ...]:
        # Ingestion can tolerate a MEDIUM high-entropy finding after redaction
        # and human review. Output cannot: returning an unknown random-looking
        # token is an immediate disclosure. Block all MEDIUM+ secret findings,
        # while keeping PII at HIGH+ so low-risk role addresses stay usable.
        secret_findings = self._blocking(
            self._secret.detect(content).findings, threshold=Severity.MEDIUM
        )
        pii_findings = self._blocking(
            self._pii.detect(content).findings, threshold=Severity.HIGH
        )
        return secret_findings + pii_findings

    def scan(self, content: str) -> OutputGuardResult:
        try:
            detector_content = self._normalize_for_detection(content)
            findings = list(self._scan_text(detector_content))
            for decoded_content in self._reversible_detection_variants(detector_content):
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
            reason="secret-like or high-confidence PII detected in model output",
        )
