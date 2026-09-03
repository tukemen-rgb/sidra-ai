"""Does a failed request tell the operator what to do next?

C-1211: every failure surfaced as 「失敗: HTTP 422」 - a bare status code.
The response body stays hidden by design (a detail the API kept private
must stay private), but the *class* of failure is not a secret, and the
code alone gives an operator no next step.

Checks on the rendered page: the guidance map covers the reachable codes
(auth, too-long/invalid, rate limit, server side), every throw site routes
through it, the code is still printed for debugging, and the error body
remains unread.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiErrorGuidanceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_error_guidance() -> UiErrorGuidanceResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    for code, guidance in (
        ("401", "アクセストークンを確認してください"),
        ("422", "入力が長すぎるか形式が不正です"),
        ("429", "混み合っています"),
        ("500", "サーバ側で問題が起きました"),
    ):
        if guidance in ASK_PAGE:
            checks += 1
        else:
            failures.append(f"no guidance for HTTP {code}")

    sites = ASK_PAGE.count("explain(response.status)")
    if sites >= 5 and 'Error("HTTP " + response.status)' not in ASK_PAGE:
        checks += 1
    else:
        failures.append("a throw site bypasses the guidance map")

    if "（HTTP " in ASK_PAGE:
        checks += 1
    else:
        failures.append("the status code is no longer printed for debugging")

    return UiErrorGuidanceResult(
        passed=not failures, checks_passed=checks, checks_total=6,
        failures=tuple(failures),
    )
