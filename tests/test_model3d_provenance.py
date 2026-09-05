"""C-1251: a generated 3D model cites its palette, not retrieval noise.

The preview footer listed whatever BM25 returned for the request (a fish model
cited revenue-model.md), but a template mesh painted with the DESIGN.md palette
is grounded in the palette, not the retrieved documents. The job no longer
passes retrieved sources as the model's evidence.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.model3d_job import build_model3d_generator
from sidra_ai.evals.model3d_provenance_is_palette import (
    evaluate_model3d_provenance_is_palette,
)


def _preview(retrieved):
    message = "魚の3Dモデルを作って"
    intent = detect_creation_intent(message)
    with TemporaryDirectory() as d:
        outcome = build_model3d_generator(d)(message, intent, retrieved)
        return Path(outcome.artifact_path).read_text(encoding="utf-8")


def test_model3d_provenance_eval_passes():
    result = evaluate_model3d_provenance_is_palette()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4


def test_retrieval_sources_not_cited_in_preview():
    html = _preview(
        [
            Fact("決済を持つ。", "tukemen-rgb/site docs/revenue-model.md"),
            Fact("北極星指標。", "tukemen-rgb/site docs/vision.md"),
        ]
    )
    assert "DESIGN.md" in html
    assert "revenue-model.md" not in html
    assert "vision.md" not in html


def test_no_retrieval_still_cites_palette():
    html = _preview(None)
    assert "DESIGN.md" in html
