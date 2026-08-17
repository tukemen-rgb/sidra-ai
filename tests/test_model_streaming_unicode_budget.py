from __future__ import annotations

import pytest

from sidra_ai.models.base import estimate_tokens
from sidra_ai.models.http_backends import _count_stream_chars, _stream_token_estimate


def _estimate_stream(chunks: list[str]) -> int:
    cjk_chars = 0
    ascii_chars = 0
    unicode_fallback_tokens = 0
    for chunk in chunks:
        cjk_chars, ascii_chars, unicode_fallback_tokens = _count_stream_chars(
            chunk,
            cjk_chars=cjk_chars,
            ascii_chars=ascii_chars,
            unicode_fallback_tokens=unicode_fallback_tokens,
        )
    return _stream_token_estimate(
        cjk_chars,
        ascii_chars,
        unicode_fallback_tokens,
    )


@pytest.mark.parametrize(
    ("chunks", "text"),
    [
        (["hello"], "hello"),
        (["ab", "cde"], "abcde"),
        (["한", "글"], "한글"),
        (["🙂", "🙂"], "🙂🙂"),
        (["ab🙂", "cd한", "字"], "ab🙂cd한字"),
    ],
)
def test_stream_token_estimate_matches_conservative_shared_heuristic(
    chunks: list[str], text: str
) -> None:
    assert _estimate_stream(chunks) == estimate_tokens(text)


def test_stream_token_estimate_keeps_unicode_fallback_conservative() -> None:
    text = "🙂🙂"

    assert estimate_tokens(text) == 8
    assert _estimate_stream(["🙂", "🙂"]) == 8
