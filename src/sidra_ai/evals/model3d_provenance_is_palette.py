"""Does a generated 3D model cite its real source, or retrieval noise?

C-1251: the 3D preview footer listed whatever BM25 returned for the request -
「魚の3Dモデルを作って」 cited revenue-model.md, vision.md,
affiliate-monetization-plan.md. But the model is a template mesh painted with
the GAMEYARD palette (docs/DESIGN.md); the retrieved documents inform neither
its shape nor its colour. Citing them is the false provenance C-1203 fixed for
documents, one artifact kind along. ``model3d_job`` passed the retrieved
sources as evidence; the model's only honest source is the palette.

The check runs the real job generator with tangential retrieved facts, reads
the preview it wrote, and confirms the footer cites the palette (DESIGN.md) and
none of the retrieved documents - and that a model built with no retrieval is
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

_TANGENTIAL = (
    "tukemen-rgb/site docs/revenue-model.md",
    "tukemen-rgb/site docs/vision.md",
)


@dataclass(frozen=True)
class Model3dProvenanceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _preview_for(retrieved_sources: tuple[str, ...]) -> str:
    from sidra_ai.creation.evidence import Fact
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.model3d_job import build_model3d_generator

    message = "魚の3Dモデルを作って"
    intent = detect_creation_intent(message)
    facts = [Fact("無関係な本文。", src) for src in retrieved_sources]
    with TemporaryDirectory() as data_dir:
        generate = build_model3d_generator(data_dir)
        outcome = generate(message, intent, facts or None)
        return Path(outcome.artifact_path).read_text(encoding="utf-8")


def evaluate_model3d_provenance_is_palette() -> Model3dProvenanceResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # Built through the job with tangential retrieval:
    with_retrieval = _preview_for(_TANGENTIAL)
    add("DESIGN.md" in with_retrieval, "footer does not cite the palette (DESIGN.md)")
    for src in _TANGENTIAL:
        name = src.split("/")[-1]
        add(name not in with_retrieval, f"footer cites unrelated retrieval: {name}")

    # Built with no retrieval - the palette citation is unchanged.
    without = _preview_for(())
    add("DESIGN.md" in without, "no-retrieval model lost its palette citation")

    return Model3dProvenanceResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=4,
        failures=tuple(failures),
    )


__all__ = ["Model3dProvenanceResult", "evaluate_model3d_provenance_is_palette"]
