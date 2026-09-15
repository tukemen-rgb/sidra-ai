"""C-1869: the secret detector catches modern issuer-prefixed token shapes.

Stripe (sk_live_/rk_live_), GitLab (glpat-), npm (npm_) and SendGrid (SG.<22>.<43>)
keys slipped through, so a bare one in an indexed doc could surface in an answer.
Added as provider patterns; the specific prefixes keep benign text safe. All
credentials here are synthetic and non-functional.
"""

from __future__ import annotations

import pytest

from sidra_ai.security.detectors import SecretDetector
from sidra_ai.evals.secret_detector_modern_tokens import (
    evaluate_secret_detector_modern_tokens,
)

_DETECTOR = SecretDetector()


def test_secret_modern_tokens_eval_passes():
    result = evaluate_secret_detector_modern_tokens()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 13


@pytest.mark.parametrize(
    "text",
    [
        "the key is sk_live_" + "A" * 24,
        "restricted rk_test_" + "B" * 20,
        "deploy token glpat-" + "C" * 20,
        "registry npm_" + "D" * 36,
        "mailer SG." + "E" * 22 + "." + "F" * 43,
    ],
)
def test_modern_secret_is_detected(text):
    assert _DETECTOR.detect(text).findings


@pytest.mark.parametrize(
    "text",
    [
        "npm run build then read npm_config_cache from the env",
        "glpat is our internal acronym for the launch plan",
        "SG. Holmes solved the case",
        "sk_live_short",
    ],
)
def test_benign_lookalike_is_not_flagged(text):
    assert not _DETECTOR.detect(text).findings


def test_existing_providers_still_caught():
    assert _DETECTOR.detect("token ghp_" + "A" * 36).findings
    assert _DETECTOR.detect("id AKIA" + "BCDEFGHIJKLMNOP1").findings
