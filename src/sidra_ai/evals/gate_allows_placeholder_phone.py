"""Does the gate let an obvious placeholder phone number through?

C-1487. The PII phone detector flags any phone-shaped digit run, including an
all-same-digit placeholder like ``000-0000-0000`` that a form spec or a design
Issue routinely carries. A single such match quarantines the whole document, so
a benign Issue ("add a phone-number input field") never reaches the index -
and during an unattended period nothing releases it from review.

A real telephone number never has all-identical digits, so skipping an
all-same-digit run costs no recall on genuine PII. This eval drives the real
``SecurityGate.inspect`` over an allowlisted GitHub source and reads the
decision: placeholders are allowed, real numbers still quarantine, and a clean
document is unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass

_REPO = "tukemen-rgb/site"

# All-same-digit placeholders a benign document carries: must be allowed.
_ALLOW = (
    "電話欄のプレースホルダは 000-0000-0000 とする。",
    "ダミー番号 00-0000-0000 を記載。",
    "0000000000 はサンプルの電話番号です。",
)

# Real telephone numbers (varied digits): must still quarantine.
_QUARANTINE = (
    "連絡先は 03-1234-5678 です。",
    "電話は09012345678までお願いします。",
    "0120-123-456 へどうぞ。",
    "call +81-90-1234-5678 now.",
)

# A clean document with no phone number at all: must be allowed (no regression).
_CLEAN = ("ダークテーマを追加してください。",)


@dataclass(frozen=True)
class PlaceholderPhoneResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_gate_allows_placeholder_phone() -> PlaceholderPhoneResult:
    from sidra_ai.security.decisions import Decision
    from sidra_ai.security.gate import SecurityGate

    gate = SecurityGate(allowed_repositories=[_REPO])

    def decision(content: str) -> Decision:
        return gate.inspect(content, source="github", repository=_REPO).decision

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for content in _ALLOW:
        add(decision(content) == Decision.ALLOW,
            f"placeholder phone was not allowed: {content!r} -> {decision(content)}")
    for content in _QUARANTINE:
        add(decision(content) == Decision.QUARANTINE,
            f"a real phone number was not quarantined: {content!r} -> {decision(content)}")
    for content in _CLEAN:
        add(decision(content) == Decision.ALLOW,
            f"a clean document was not allowed: {content!r} -> {decision(content)}")

    total = len(_ALLOW) + len(_QUARANTINE) + len(_CLEAN)
    return PlaceholderPhoneResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["PlaceholderPhoneResult", "evaluate_gate_allows_placeholder_phone"]
