"""C-1610: the GIF summary must not point a CLI reader at the web file list.

Every other generator's summary is channel-neutral - it says to open the file,
and each channel surfaces where it is. The GIF summary alone said 「生成ファイル
一覧からダウンロードして…」, which names the web UI's file list; a sidra-ask
terminal reader has no such list. The fix keeps 「ブラウザや画像ビューアーで
開けます。」 and drops the web-only navigation.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.evals.gif_summary_channel_neutral import (
    evaluate_gif_summary_channel_neutral,
)


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="gif-channel-test-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def _answer(service, request: str) -> str:
    return str((service.chat(request) or {}).get("answer") or "")


def test_gif_summary_channel_neutral_eval_passes():
    result = evaluate_gif_summary_channel_neutral()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_gif_summary_has_no_web_only_list_reference():
    service = _build_service()
    for request in ("魚のGIFを作って", "GIFを作って"):
        answer = _answer(service, request)
        assert "生成ファイル一覧" not in answer, answer
        assert "ブラウザ" in answer, answer


def test_gif_summary_still_discloses_default_motif():
    service = _build_service()
    answer = _answer(service, "GIFを作って")
    assert "依頼に合う絵柄が無かったので" in answer
    assert "絵柄" in answer


def test_other_generators_have_no_web_only_list_reference():
    service = _build_service()
    for request in ("螺旋のアートを作って", "レースゲームを作って",
                    "舟の3Dモデルを作って", "提案スライドを作って"):
        assert "生成ファイル一覧" not in _answer(service, request), request
