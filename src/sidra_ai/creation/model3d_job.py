"""The 3D-model generator as the router sees it.

Same split as the game and deck jobs: :mod:`sidra_ai.creation.models3d` is a
library with no opinion about HTTP or artifact directories, and this file
holds the one callable the router needs. The summary reports the validator's
verdict, not the fact that files were written.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.creation.art import names_color
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.models3d import (
    DEFAULT_SHAPE,
    SHAPE_LABELS,
    generate_model3d,
    save_model3d,
    validate_model3d,
)
from sidra_ai.creation.router import CreationOutcome


def build_model3d_generator(data_dir: str | Path):
    def generate(
        message: str,
        intent: CreationIntent,
        retrieved: list[Fact] | None = None,
    ) -> CreationOutcome:
        # C-1251: the model is a template mesh painted with the DESIGN.md
        # palette; the retrieved documents inform neither its shape nor its
        # colour, so listing them as 「出典」 in the preview is the false
        # provenance C-1203 removed from documents. Let generate_model3d cite
        # its real source (the palette) rather than whatever BM25 returned.
        model = generate_model3d(message)
        verdict = validate_model3d(model)
        paths = save_model3d(model, data_dir)
        if verdict["valid"]:
            shape_label = SHAPE_LABELS.get(model.shape, model.shape)
            summary = (
                f"「{model.title}」の 3D モデルを作りました"
                f"（形状: {shape_label}、low-poly、頂点 {verdict['vertices']}・"
                f"面 {verdict['faces']}）。"
                ".obj は Windows の 3D ビューアーでそのまま開けます。"
                "プレビュー HTML はブラウザで回転表示できます。"
            )
            # The request named no shape, so the fish default was used. Say so
            # and list the shapes that can be asked for - a reader who asked for
            # 「猫」 got a fish mesh and would otherwise never learn the subject
            # was not modelled or what they could pick (C-1267). Not a claim the
            # subject can't be modelled: the three shapes are abstract, so the
            # honest fact is just "you didn't name one, here is what you got and
            # what you can pick".
            if not model.shape_named:
                choices = " / ".join(SHAPE_LABELS.values())
                summary += (
                    f"依頼に合う形状が無かったので、既定の"
                    f"「{SHAPE_LABELS[DEFAULT_SHAPE]}」にしました。"
                    f"いま作れる形状は {choices} です。"
                )
            # The request named a colour, but the palette is fixed, so 「青い」 was
            # painted the same as every other model. Say the colour was not
            # applied rather than let the title imply it was - the same honesty
            # art got (C-1272, extending C-1271 to the 3D generator).
            if names_color(message):
                summary += (
                    "依頼にあった色は今の配色に反映していません。"
                    "3D モデルは固定の配色で描いています。"
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
