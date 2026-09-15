"""Does the secret detector catch modern issuer-prefixed token shapes?

C-1869. ``SecretDetector`` carries a provider list justified by "these prefixes
are reserved by their issuers" - github ``ghp_``, aws ``AKIA``, openai ``sk-``,
google ``AIza``, slack ``xox`` and so on. Four common modern formats with the
same kind of reserved prefix were missing, so a bare one in an indexed document
was neither quarantined at ingestion nor redacted in output, and could surface
in an answer excerpt:

* Stripe secret / restricted keys ``sk_live_`` ``sk_test_`` ``rk_live_`` ``rk_test_``;
* GitLab personal access tokens ``glpat-``;
* npm automation tokens ``npm_`` + 36 chars;
* SendGrid API keys ``SG.<22>.<43>``.

Adding them is a gap-fill in the detector's own stated approach, not a policy
change: the prefixes are specific, so a benign 「npm_config_cache」 or a prose
「SG. Holmes」 is not matched (measured below).

Driven through the real ``SecretDetector``. All credentials here are synthetic
and non-functional.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.security.detectors import SecretDetector

_DETECTOR = SecretDetector()

#: (label, text) - a bare modern token that MUST now be detected.
_MUST_CATCH: tuple[tuple[str, str], ...] = (
    ("stripe_sk_live", "the key is sk_live_" + "A" * 24),
    ("stripe_rk_test", "restricted rk_test_" + "B" * 20),
    ("gitlab_glpat", "deploy token glpat-" + "C" * 20),
    ("npm_token", "registry npm_" + "D" * 36),
    ("sendgrid", "mailer SG." + "E" * 22 + "." + "F" * 43),
)

#: Existing providers - must STILL be caught (no regression from the addition).
_REGRESSION_CATCH: tuple[tuple[str, str], ...] = (
    ("github", "token ghp_" + "A" * 36),
    ("aws", "id AKIA" + "BCDEFGHIJKLMNOP1"),
    ("openai", "key sk-" + "A" * 40),
)

#: Benign lookalikes - must NOT be flagged (a new prefix must not false-positive).
_MUST_NOT: tuple[str, ...] = (
    "npm run build then read npm_config_cache from the env",
    "the sdk_livecycle method returns a handle",
    "glpat is our internal acronym for the launch plan",
    "SG. Holmes solved the case",
    "sk_live_short",  # under the length floor
)


@dataclass(frozen=True)
class SecretModernResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_secret_detector_modern_tokens() -> SecretModernResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for label, text in _MUST_CATCH:
        add(bool(_DETECTOR.detect(text).findings), f"missed a {label} secret: {text[:24]!r}…")
    for label, text in _REGRESSION_CATCH:
        add(bool(_DETECTOR.detect(text).findings), f"regressed {label} detection: {text[:24]!r}…")
    for text in _MUST_NOT:
        add(not _DETECTOR.detect(text).findings, f"false positive on benign text: {text!r}")

    total = len(_MUST_CATCH) + len(_REGRESSION_CATCH) + len(_MUST_NOT)
    return SecretModernResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["SecretModernResult", "evaluate_secret_detector_modern_tokens"]
