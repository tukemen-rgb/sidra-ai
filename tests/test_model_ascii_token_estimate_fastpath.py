"""ASCII fast-path regressions for local context token estimation."""

from __future__ import annotations

import pytest

import sidra_ai.models.base as model_base
from sidra_ai.models.base import estimate_tokens


def test_ascii_fast_path_preserves_partial_group_rounding() -> None:
    for length in range(1, 33):
        text = "x" * length
        assert estimate_tokens(text) == (length + 3) // 4


def test_ascii_fast_path_preserves_all_ascii_code_points() -> None:
    text = "".join(chr(codepoint) for codepoint in range(128))
    assert text.isascii()
    assert estimate_tokens(text) == (len(text) + 3) // 4


def test_ascii_fast_path_skips_unicode_classifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def classifier_must_not_run(_char: str) -> bool:
        raise AssertionError("ASCII fast path should not enter the Unicode loop")

    monkeypatch.setattr(model_base, "_is_cjk_like", classifier_must_not_run)

    text = "repository status and source code\n" * 4096
    assert estimate_tokens(text) == (len(text) + 3) // 4


def test_non_ascii_path_keeps_existing_conservative_semantics() -> None:
    assert estimate_tokens("日abcde") == 3
    assert estimate_tokens("안녕") == 2
    assert estimate_tokens("😀") == len("😀".encode("utf-8"))
    assert estimate_tokens("café") == 3
