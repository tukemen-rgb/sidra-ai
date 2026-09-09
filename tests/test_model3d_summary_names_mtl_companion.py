"""C-1617: the 3D summary must point at the companion .mtl for colours.

A model is three files; the .obj's colours resolve only from the .mtl beside it.
The summary named the .obj and preview but not the .mtl, so a non-expert opening
the .obj alone got a silently colourless model. The summary now names the .mtl
and says to keep it with the .obj.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.evals.model3d_summary_names_mtl_companion import (
    evaluate_model3d_summary_names_mtl_companion,
)


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="m3d-mtl-test-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def _answer(service, request: str) -> str:
    return str((service.chat(request) or {}).get("answer") or "")


def test_eval_passes():
    result = evaluate_model3d_summary_names_mtl_companion()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_summary_names_the_mtl_companion():
    service = _build_service()
    for request in ("魚の3Dモデルを作って", "地形の3Dモデルを作って",
                    "ドラゴンの3Dモデルを作って"):
        answer = _answer(service, request)
        assert ".mtl" in answer, request
        assert "一緒に置いて" in answer, request


def test_existing_summary_content_survives():
    service = _build_service()
    fish = _answer(service, "魚の3Dモデルを作って")
    assert "頂点" in fish and "面" in fish
    assert ".obj" in fish and "プレビュー" in fish
    assert "依頼に合う形状が無かったので" not in fish  # named shape: no default note
    dragon = _answer(service, "ドラゴンの3Dモデルを作って")
    assert "依頼に合う形状が無かったので" in dragon  # unnamed: default note kept
