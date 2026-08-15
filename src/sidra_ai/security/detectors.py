"""Detectors used by the security gate.

Each detector is a small, independently testable unit that returns
:class:`~sidra_ai.security.decisions.Finding` objects plus, where relevant,
redaction spans. Detectors never mutate content themselves - the gate decides
what to do with what they report.

None of the patterns below contain a real credential. They describe the
*shape* of credentials only.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence

from sidra_ai.security.decisions import Finding, FindingCategory, Severity
from sidra_ai.security.redaction import excerpt


@dataclass(frozen=True)
class DetectionOutput:
    findings: tuple[Finding, ...] = ()
    spans: tuple[tuple[int, int, str], ...] = ()
    """``(start, end, label)`` regions the gate may redact."""


class Detector(Protocol):
    name: str

    def detect(self, content: str) -> DetectionOutput:  # pragma: no cover - protocol
        ...


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Pattern:
    label: str
    regex: re.Pattern[str]
    reason: str
    severity: Severity = Severity.CRITICAL
    group: int = 0


#: Provider-specific credential shapes. Matching one of these is high
#: confidence: these prefixes are reserved by their issuers.
_SECRET_PATTERNS: tuple[_Pattern, ...] = (
    _Pattern(
        "github_token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),
        "GitHub personal/OAuth access token shape",
    ),
    _Pattern(
        "github_fine_grained_token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        "GitHub fine-grained token shape",
    ),
    _Pattern(
        "aws_access_key_id",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "AWS access key id shape",
    ),
    _Pattern(
        "anthropic_api_key",
        re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b"),
        "Anthropic API key shape",
    ),
    _Pattern(
        "openai_api_key",
        re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_\-]{20,}\b"),
        "OpenAI-style API key shape",
    ),
    _Pattern(
        "slack_token",
        re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"),
        "Slack token shape",
    ),
    _Pattern(
        "google_api_key",
        re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        "Google API key shape",
    ),
    _Pattern(
        "private_key_block",
        re.compile(
            r"-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----.*?-----END(?: [A-Z]+)? "
            r"PRIVATE KEY-----",
            re.DOTALL,
        ),
        "PEM private key block",
    ),
    _Pattern(
        "json_web_token",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
        "JSON Web Token shape",
        severity=Severity.HIGH,
    ),
    _Pattern(
        "basic_auth_url",
        re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:([^\s/@]{4,})@"),
        "credentials embedded in a URL",
        group=1,
    ),
)

#: ``password = "..."`` style assignments. The value group is redacted.
_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    \b(?P<key>
        (?:api[_\-\s]?key)|(?:secret[_\-\s]?key)|(?:access[_\-\s]?token)
        |(?:auth[_\-\s]?token)|password|passwd|secret|token|credential
        |client[_\-\s]?secret|private[_\-\s]?key
    )
    ["']?\s*[:=]\s*
    (?P<quote>["'])?
    (?P<value>[^\s"',;]{6,})
    (?(quote)["'])
    """
)

#: Values that look like a credential assignment but are obviously not one.
_PLACEHOLDER_VALUES = frozenset(
    {
        "changeme",
        "example",
        "placeholder",
        "redacted",
        "none",
        "null",
        "true",
        "false",
        "your_token_here",
        "your-token-here",
        "xxxxxxxx",
        "todo",
        "unset",
        "dummy",
        "fake",
    }
)


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in _PLACEHOLDER_VALUES:
        return True
    # Code expressions and template placeholders, e.g. os.getenv("X"),
    # os.environ["X"], ${VAR}, {{ secret }}, <your-token>. A real credential
    # does not contain these characters.
    if any(char in value for char in "([{$<"):
        return True
    if set(lowered) <= {"x", "*", ".", "-", "_"}:
        return True
    # Names of environment variables, not their values.
    if re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", value.strip()):
        return True
    return False


def shannon_entropy(value: str) -> float:
    """Bits of entropy per character."""

    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


_HIGH_ENTROPY_CANDIDATE = re.compile(r"\b[A-Za-z0-9+/_\-]{32,}={0,2}\b")


class SecretDetector:
    """Finds credential-shaped strings.

    Three layers, in decreasing confidence: provider-specific prefixes,
    ``key = value`` assignments with credential-ish key names, and
    high-entropy blobs. Only the first two are treated as critical; entropy
    alone is reported at medium severity because it false-positives on
    hashes, base64 images and minified assets.
    """

    name = "secret"

    def __init__(self, entropy_threshold: float = 4.2) -> None:
        self.entropy_threshold = entropy_threshold

    def detect(self, content: str) -> DetectionOutput:
        findings: list[Finding] = []
        spans: list[tuple[int, int, str]] = []
        seen: set[tuple[int, int]] = set()

        for pattern in _SECRET_PATTERNS:
            for match in pattern.regex.finditer(content):
                start, end = match.span(pattern.group)
                if (start, end) in seen:
                    continue
                seen.add((start, end))
                spans.append((start, end, pattern.label))
                findings.append(
                    Finding(
                        category=FindingCategory.SECRET,
                        severity=pattern.severity,
                        detector=pattern.label,
                        reason=pattern.reason,
                        evidence=excerpt(content, start, end),
                        start=start,
                        end=end,
                    )
                )

        for match in _ASSIGNMENT_PATTERN.finditer(content):
            value = match.group("value")
            start, end = match.span("value")
            if (start, end) in seen or _looks_like_placeholder(value):
                continue
            seen.add((start, end))
            spans.append((start, end, "assigned_secret"))
            findings.append(
                Finding(
                    category=FindingCategory.SECRET,
                    severity=Severity.CRITICAL,
                    detector="assigned_secret",
                    reason=(
                        f"value assigned to credential-like key "
                        f"{match.group('key').strip().lower()!r}"
                    ),
                    evidence=excerpt(content, start, end),
                    start=start,
                    end=end,
                )
            )

        for match in _HIGH_ENTROPY_CANDIDATE.finditer(content):
            start, end = match.span()
            if any(s <= start and end <= e for s, e, _ in spans):
                continue
            candidate = match.group()
            if shannon_entropy(candidate) < self.entropy_threshold:
                continue
            spans.append((start, end, "high_entropy"))
            findings.append(
                Finding(
                    category=FindingCategory.SECRET,
                    severity=Severity.MEDIUM,
                    detector="high_entropy",
                    reason=(
                        "high-entropy string; may be a credential, may be a "
                        "hash or encoded asset - needs human confirmation"
                    ),
                    evidence=excerpt(content, start, end),
                    start=start,
                    end=end,
                    metadata={"entropy": round(shannon_entropy(candidate), 3)},
                )
            )

        return DetectionOutput(tuple(findings), tuple(spans))


# ---------------------------------------------------------------------------
# PII
# ---------------------------------------------------------------------------

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_JP = re.compile(r"(?<![\d\-])0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}(?![\d\-])")
_PHONE_INTL = re.compile(r"(?<![\d\-])\+\d{1,3}[-\s]?\d{1,4}[-\s]?\d{3,4}[-\s]?\d{3,4}(?![\d\-])")
_CARD_CANDIDATE = re.compile(r"(?<![\d\-])(?:\d[ \-]?){13,19}(?![\d\-])")
_MY_NUMBER = re.compile(r"(?<![\d\-])\d{4}[-\s]?\d{4}[-\s]?\d{4}(?![\d\-])")

#: Emails that identify a service, not a person.
_ROLE_EMAIL_LOCALPARTS = frozenset(
    {"noreply", "no-reply", "support", "info", "admin", "hello", "contact", "security"}
)


def _luhn_ok(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        digit = int(char)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


class PIIDetector:
    """Finds personal information.

    GitHub metadata is full of ``users.noreply.github.com`` addresses, so
    role/noreply addresses are reported at low severity and do not on their
    own quarantine a document.
    """

    name = "pii"

    def detect(self, content: str) -> DetectionOutput:
        findings: list[Finding] = []
        spans: list[tuple[int, int, str]] = []

        for match in _EMAIL.finditer(content):
            start, end = match.span()
            address = match.group()
            local = address.split("@", 1)[0].lower()
            is_role = local in _ROLE_EMAIL_LOCALPARTS or "noreply" in address.lower()
            spans.append((start, end, "email"))
            findings.append(
                Finding(
                    category=FindingCategory.PII,
                    severity=Severity.LOW if is_role else Severity.HIGH,
                    detector="email_role" if is_role else "email",
                    reason=(
                        "role/noreply email address"
                        if is_role
                        else "email address identifying a person"
                    ),
                    evidence=excerpt(content, start, end),
                    start=start,
                    end=end,
                )
            )

        for regex, label in ((_PHONE_JP, "phone_jp"), (_PHONE_INTL, "phone_intl")):
            for match in regex.finditer(content):
                start, end = match.span()
                if any(s <= start and end <= e for s, e, _ in spans):
                    continue
                spans.append((start, end, label))
                findings.append(
                    Finding(
                        category=FindingCategory.PII,
                        severity=Severity.HIGH,
                        detector=label,
                        reason="telephone number shape",
                        evidence=excerpt(content, start, end),
                        start=start,
                        end=end,
                    )
                )

        for match in _CARD_CANDIDATE.finditer(content):
            digits = re.sub(r"[ \-]", "", match.group())
            if not (13 <= len(digits) <= 19) or not _luhn_ok(digits):
                continue
            start, end = match.span()
            spans.append((start, end, "payment_card"))
            findings.append(
                Finding(
                    category=FindingCategory.PII,
                    severity=Severity.CRITICAL,
                    detector="payment_card",
                    reason="payment card number (passes Luhn check)",
                    evidence=excerpt(content, start, end),
                    start=start,
                    end=end,
                )
            )

        for match in _MY_NUMBER.finditer(content):
            start, end = match.span()
            if any(s <= start and end <= e for s, e, _ in spans):
                continue
            spans.append((start, end, "national_id"))
            findings.append(
                Finding(
                    category=FindingCategory.PII,
                    severity=Severity.MEDIUM,
                    detector="national_id_candidate",
                    reason="12-digit sequence; may be a Japanese My Number",
                    evidence=excerpt(content, start, end),
                    start=start,
                    end=end,
                )
            )

        return DetectionOutput(tuple(findings), tuple(spans))


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------

#: English and Japanese phrasings of "stop being a tool, start being an agent
#: under my control". Detection is heuristic and deliberately noisy: a false
#: positive costs a quarantine review, a false negative costs control of the
#: model.
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str], Severity, str], ...] = (
    (
        "override_instructions",
        re.compile(
            r"(?i)\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b"
            r"(previous|prior|above|earlier|all|any)\b[^.\n]{0,20}\b"
            r"(instruction|prompt|rule|direction|context)s?\b"
        ),
        Severity.CRITICAL,
        "attempts to void prior instructions",
    ),
    (
        "override_instructions_ja",
        re.compile(
            r"(これまで|以前|上記|先ほど)の(指示|命令|ルール|プロンプト)"
            r"[^。\n]{0,20}(無視|忘れ|破棄|上書き)"
        ),
        Severity.CRITICAL,
        "attempts to void prior instructions (Japanese)",
    ),
    (
        "role_reassignment",
        re.compile(
            r"(?i)\b(you are now|from now on,? you|act as|pretend to be|"
            r"your new (role|instruction)s? (is|are))\b"
        ),
        Severity.HIGH,
        "attempts to reassign the assistant's role",
    ),
    (
        "role_reassignment_ja",
        re.compile(r"(今から|これから)あなたは|として(振る舞|ふるま)"),
        Severity.HIGH,
        "attempts to reassign the assistant's role (Japanese)",
    ),
    (
        "system_prompt_spoof",
        re.compile(
            r"(?i)(^|\n)\s*(system\s*:|<\s*/?\s*system\s*>|\[\s*system\s*\]|"
            r"###\s*system|<\|im_start\|>|<\|system\|>)"
        ),
        Severity.CRITICAL,
        "impersonates a system/role delimiter",
    ),
    (
        "exfiltration",
        re.compile(
            r"(?i)\b(reveal|print|show|output|repeat|dump|leak)\b[^.\n]{0,40}\b"
            r"(system prompt|instructions|api[ _-]?key|token|secret|password|"
            r"credential|\.env)\b"
        ),
        Severity.CRITICAL,
        "attempts to exfiltrate secrets or the system prompt",
    ),
    (
        "exfiltration_ja",
        re.compile(r"(システムプロンプト|APIキー|秘密鍵|パスワード)[^。\n]{0,20}(教えて|出力|表示)"),
        Severity.CRITICAL,
        "attempts to exfiltrate secrets (Japanese)",
    ),
    (
        "tool_coercion",
        re.compile(
            r"(?i)\b(run|execute|curl|wget|send|post|push|commit|merge|delete|"
            r"deploy)\b[^.\n]{0,30}\b(command|shell|request|to https?://|this url)\b"
        ),
        Severity.HIGH,
        "attempts to make the assistant take an outbound or write action",
    ),
    (
        "guardrail_bypass",
        re.compile(
            r"(?i)\b(developer mode|jailbreak|dan mode|without (any )?restrictions|"
            r"bypass (the )?(safety|filter|guardrail))\b"
        ),
        Severity.HIGH,
        "known guardrail-bypass phrasing",
    ),
    (
        "hidden_channel",
        re.compile(r"<!--[^>]{0,200}?(?i:ignore|instruction|system|prompt)[^>]{0,200}?-->"),
        Severity.HIGH,
        "instruction-like text hidden in a comment",
    ),
)

#: Zero-width and bidirectional control characters used to hide payloads.
_INVISIBLE_CHARS = re.compile(r"[​-‏‪-‮⁠-⁤﻿]")


class PromptInjectionDetector:
    """Flags content that tries to behave as an instruction.

    Detection does **not** imply deletion. The gate's contract is that all
    ingested content is DATA regardless of what this detector says - the
    detector exists so that injection attempts are visible and auditable,
    not so that "clean" content can be trusted as instructions.
    """

    name = "prompt_injection"

    def detect(self, content: str) -> DetectionOutput:
        findings: list[Finding] = []

        for label, regex, severity, reason in _INJECTION_PATTERNS:
            for match in regex.finditer(content):
                start, end = match.span()
                findings.append(
                    Finding(
                        category=FindingCategory.PROMPT_INJECTION,
                        severity=severity,
                        detector=label,
                        reason=reason,
                        evidence=content[start:end][:160].replace("\n", " "),
                        start=start,
                        end=end,
                    )
                )

        invisible = _INVISIBLE_CHARS.findall(content)
        if invisible:
            findings.append(
                Finding(
                    category=FindingCategory.PROMPT_INJECTION,
                    severity=Severity.MEDIUM,
                    detector="invisible_characters",
                    reason=(
                        f"{len(invisible)} zero-width/bidi control characters; "
                        "commonly used to hide instructions from human review"
                    ),
                    metadata={"count": len(invisible)},
                )
            )

        return DetectionOutput(tuple(findings))


# ---------------------------------------------------------------------------
# Size and source
# ---------------------------------------------------------------------------

class OversizeDetector:
    """Rejects inputs beyond the configured byte budget.

    Size is measured in UTF-8 bytes, not characters: a Japanese document is
    roughly three bytes per character and would otherwise slip past a
    character-based limit.
    """

    name = "oversize"

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes

    def detect(self, content: str) -> DetectionOutput:
        size = len(content.encode("utf-8"))
        if size <= self.max_bytes:
            return DetectionOutput()
        return DetectionOutput(
            (
                Finding(
                    category=FindingCategory.OVERSIZED_INPUT,
                    severity=Severity.HIGH,
                    detector="byte_budget",
                    reason=f"{size} bytes exceeds the {self.max_bytes} byte budget",
                    metadata={"size_bytes": size, "max_bytes": self.max_bytes},
                ),
            )
        )


class SourceAllowlistDetector:
    """Rejects content from repositories/sources that are not allowlisted."""

    name = "source_allowlist"

    def __init__(self, allowed_repositories: Sequence[str], allowed_sources: Iterable[str] = ("github", "operator")) -> None:
        self.allowed_repositories = {r.lower() for r in allowed_repositories}
        self.allowed_sources = {s.lower() for s in allowed_sources}

    def check(self, *, source: str, repository: str) -> DetectionOutput:
        findings: list[Finding] = []
        if source.lower() not in self.allowed_sources:
            findings.append(
                Finding(
                    category=FindingCategory.UNPERMITTED_SOURCE,
                    severity=Severity.CRITICAL,
                    detector="source",
                    reason=f"source {source!r} is not on the allowlist",
                    metadata={"source": source},
                )
            )
        if repository and repository.lower() not in self.allowed_repositories:
            findings.append(
                Finding(
                    category=FindingCategory.UNPERMITTED_SOURCE,
                    severity=Severity.CRITICAL,
                    detector="repository",
                    reason=f"repository {repository!r} is not on the allowlist",
                    metadata={"repository": repository},
                )
            )
        return DetectionOutput(tuple(findings))

    def detect(self, content: str) -> DetectionOutput:
        """Content alone carries no source; use :meth:`check` instead."""

        return DetectionOutput()
