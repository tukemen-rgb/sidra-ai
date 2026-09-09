"""C-1619: the art summary names its pattern in Japanese, not the internal key.

The summary led with 「パターン: {key}」 (flow/orbits) on a Japanese page while
3D/GIF and the summary's own default note use Japanese labels. It now uses
PATTERN_LABELS, so 「パターン: 軌道」/「パターン: フロー」.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.evals.art_summary_pattern_label_japanese import (
    evaluate_art_summary_pattern_label_japanese,
)


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="art-label-test-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def _answer(service, request: str) -> str:
    return str((service.chat(request) or {}).get("answer") or "")


def test_eval_passes():
    result = evaluate_art_summary_pattern_label_japanese()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_named_pattern_uses_japanese_label():
    service = _build_service()
    orbit = _answer(service, "軌道のアートを作って")
    assert "パターン: 軌道" in orbit
    assert "orbits" not in orbit
    flow = _answer(service, "フローのアートを作って")
    assert "パターン: フロー" in flow
    assert "flow" not in flow


def test_default_pattern_labelled_and_still_disclosed():
    service = _build_service()
    default = _answer(service, "螺旋のアートを作って")
    assert "パターン: フロー" in default
    assert "flow" not in default
    assert "指定できるパターンは フロー / 軌道 です" in default
