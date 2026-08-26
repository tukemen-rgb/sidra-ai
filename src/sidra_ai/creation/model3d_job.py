"""The 3D-model generator as the router sees it.

Same split as the game and deck jobs: :mod:`sidra_ai.creation.models3d` is a
library with no opinion about HTTP or artifact directories, and this file
holds the one callable the router needs. The summary reports the validator's
verdict, not the fact that files were written.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.models3d import generate_model3d, save_model3d, validate_model3d
from sidra_ai.creation.router import CreationOutcome


def build_model3d_generator(data_dir: str | Path):
    def generate(
        message: str,
        intent: CreationIntent,
        retrieved: list[Fact] | None = None,
    ) -> CreationOutcome:
        evidence = [fact.source for fact in (retrieved or []) if fact.source]
        model = generate_model3d(message, evidence=evidence or None)
        verdict = validate_model3d(model)
        paths = save_model3d(model, data_dir)
        if verdict["valid"]:
            summary = (
                f"「{model.title}」の 3D モデルを作りました"
                f"（low-poly、頂点 {verdict['vertices']}・面 {verdict['faces']}）。"
                ".obj は Windows の 3D ビューアーでそのまま開けます。"
                "プレビュー HTML はブラウザで回転表示できます。"
            )
        else:
            summary = (
                f"「{model.title}」の 3D モデルを作りましたが、検証に落ちています: "
                + "、".join(str(f) for f in verdict["failures"])
            )
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(paths["preview"]),
            details={
                "shape": model.shape,
                "seed": model.seed,
                "valid": verdict["valid"],
                "vertices": verdict["vertices"],
                "faces": verdict["faces"],
                "js_checker": verdict["js_checker"],
                "obj_path": str(paths["obj"]),
                "mtl_path": str(paths["mtl"]),
            },
        )

    return generate


__all__ = ["build_model3d_generator"]
