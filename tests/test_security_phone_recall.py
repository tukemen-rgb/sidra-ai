"""Regression coverage for phone-detector precision without silent recall loss."""

from sidra_ai.security.detectors import PIIDetector


def _labels(content: str) -> set[str]:
    return {finding.detector for finding in PIIDetector().detect(content).findings}


def test_international_phone_tuning_preserves_existing_eight_digit_shape() -> None:
    """False-positive tuning must not narrow the pre-existing regex recall floor."""

    assert "phone_intl" in _labels("Contact: +1-2-345-678")


def test_short_numeric_git_sha_is_not_a_japanese_phone() -> None:
    assert "phone_jp" not in _labels("Verified commit 0965092")


def test_japanese_phone_recall_is_preserved() -> None:
    assert "phone_jp" in _labels("Office: 03-1234-5678")
    assert "phone_jp" in _labels("Mobile: 09012345678")
