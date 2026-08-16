"""Release-gate Security detector precision without sacrificing recall.

Claude's measured false-positive work found two operationally important noise
sources in the real SIDRA repositories: numeric git short SHAs being treated as
Japanese phone numbers, and TypeScript declarations/autocomplete metadata being
treated as assigned secrets.  A follow-up review also caught an unrelated
narrowing of the pre-existing international-phone recall floor.

This suite protects both sides of that trade-off at the real ``SecurityGate``
boundary so future detector tuning cannot buy precision by silently losing
recall.
"""

from __future__ import annotations

from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.security.decisions import Decision, FindingCategory
from sidra_ai.security.gate import GatePolicy, SecurityGate


def _gate() -> SecurityGate:
    return SecurityGate(
        GatePolicy(max_input_bytes=512 * 1024),
        allowed_repositories=("tukemen-rgb/sidra-ai",),
    )


def run_gate_precision_recall_suite() -> tuple[EvalOutcome, ...]:
    gate = _gate()
    outcomes: list[EvalOutcome] = []

    precision_failures: list[str] = []
    sha_result = gate.inspect(
        "Release notes reference git short SHA 0965092 in prose.",
        source="github",
        repository="tukemen-rgb/sidra-ai",
    )
    if sha_result.decision is not Decision.ALLOW:
        precision_failures.append(
            f"numeric git short SHA was refused ({sha_result.decision.value})"
        )
    if any(f.detector in {"phone_jp", "phone_intl"} for f in sha_result.findings):
        precision_failures.append("numeric git short SHA was classified as a phone")

    typescript_result = gate.inspect(
        'interface AuthInput { token: string; password: string }\n'
        '<input autocomplete="current-password">',
        source="github",
        repository="tukemen-rgb/sidra-ai",
    )
    if typescript_result.decision is not Decision.ALLOW:
        precision_failures.append(
            "TypeScript/auth metadata was refused "
            f"({typescript_result.decision.value})"
        )
    if any(
        finding.category is FindingCategory.SECRET
        for finding in typescript_result.findings
    ):
        precision_failures.append("TypeScript/auth metadata was classified as a secret")

    outcomes.append(
        EvalOutcome(
            case_name="security_gate_measured_false_positive_precision",
            passed=not precision_failures,
            detail="real-repository false-positive shapes remain usable",
            failures=tuple(precision_failures),
        )
    )

    recall_failures: list[str] = []
    recall_cases = (
        ("03-1234-5678", "phone_jp"),
        ("09012345678", "phone_jp"),
        ("+1-2-345-678", "phone_intl"),
    )
    for value, detector in recall_cases:
        result = gate.inspect(
            f"Synthetic contact value for detector regression: {value}",
            source="github",
            repository="tukemen-rgb/sidra-ai",
        )
        if result.decision is not Decision.QUARANTINE:
            recall_failures.append(
                f"{detector} recall shape was not quarantined ({result.decision.value})"
            )
        if not any(f.detector == detector for f in result.findings):
            recall_failures.append(f"{detector} finding disappeared for recall shape")
        if value in result.content:
            recall_failures.append(f"{detector} value survived gate redaction")

    outcomes.append(
        EvalOutcome(
            case_name="security_gate_phone_recall_floor",
            passed=not recall_failures,
            detail="precision tuning preserves Japanese and pre-existing international recall",
            failures=tuple(recall_failures),
        )
    )

    return tuple(outcomes)
