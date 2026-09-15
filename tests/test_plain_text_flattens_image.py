"""C-1840: plain_text flattens a Markdown image to its alt text.

The image sibling of C-1227. plain_text flattened a link but left an image's
leading 「!」 (「![logo](url)」→「!logo」), and a bare badge 「![](url)」 survived
whole, leaking its URL into forwarded artifacts. Images now collapse to alt text
before the link rule; the link rule is unchanged.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.plain_text_flattens_image import (
    evaluate_plain_text_flattens_image,
)


def test_plain_text_image_eval_passes():
    result = evaluate_plain_text_flattens_image()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("![logo](https://x/l.png)", "logo"),
        ("![CI passing](https://ci/badge.svg) 稼働中", "CI passing 稼働中"),
        ("![](https://x/img.png)後続", "後続"),
        ("詳細は![図](https://a/i.png)を参照", "詳細は図を参照"),
    ],
)
def test_image_flattens_to_alt_without_marker_or_url(raw, expected):
    got = plain_text(raw)
    assert got == expected
    assert "![" not in got and "https://" not in got


def test_link_flattening_still_works():
    assert plain_text("詳細は[管理画面](https://a/d)を参照") == "詳細は管理画面を参照"
