"""Does the gate let all-same-digit placeholder My Numbers and cards through?

C-1489, the follow-through to C-1487 (which exempted all-same-digit phone
placeholders but left national_id and payment_card as "a separate class"). A
form spec or a design Issue routinely carries 「000000000000」 as a My Number
placeholder or 「0000 0000 0000 0000」 as a card placeholder (all zeros even
passes Luhn), and a single such match quarantines the whole benign document.

A real My Number or card never has all-identical digits, so skipping an
all-same-digit run costs no recall. This eval drives the real
``SecurityGate.inspect`` over an allowlisted GitHub source and reads the
decision: placeholders are allowed, real values still quarantine, and the phone
exemption from C-1487 is unregressed.
"""

from __future__ import annotations

from dataclasses import dataclass

_REPO = "tukemen-rgb/site"

# All-same-digit numeric placeholders a benign document carries: must be allowed.
_ALLOW = (
    "マイナンバー欄の例: 000000000000",
    "マイナンバーのプレースホルダは 0000-0000-0000 とする",
    "カード番号のプレースホルダは 0000 0000 0000 0000",
    "テストカード 0000-0000-0000-0000 を使う",
)

# Real values (varied digits): must still quarantine.
_QUARANTINE = (
    "マイナンバー記入例 1234-5678-9012",
    "カードは 4111 1111 1111 1111 です",
    "連絡先は 03-1234-5678 です",  # phone, C-1487 must be unregressed
)

# A clean document with no PII at all: must be allowed (no regression).
_CLEAN = ("ダークテーマを追加してください。",)


@dataclass(frozen=True)
class PlaceholderNumberResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_gate_allows_placeholder_national_id_and_card() -> PlaceholderNumberResult:
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
            f"placeholder number was not allowed: {content!r} -> {decision(content)}")
    for content in _QUARANTINE:
        add(decision(content) == Decision.QUARANTINE,
            f"a real value was not quarantined: {content!r} -> {decision(content)}")
    for content in _CLEAN:
        add(decision(content) == Decision.ALLOW,
            f"a clean document was not allowed: {content!r} -> {decision(content)}")

    total = len(_ALLOW) + len(_QUARANTINE) + len(_CLEAN)
    return PlaceholderNumberResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "PlaceholderNumberResult",
    "evaluate_gate_allows_placeholder_national_id_and_card",
]
