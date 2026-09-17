"""The 3D-model generator as the router sees it.

Same split as the game and deck jobs: :mod:`sidra_ai.creation.models3d` is a
library with no opinion about HTTP or artifact directories, and this file
holds the one callable the router needs. The summary reports the validator's
verdict, not the fact that files were written.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.models.echo import _reply_in_japanese

from sidra_ai.creation.art import names_color
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.models3d import (
    count_note,
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
        # C-1932: the product's own rule for which language the reply
        # takes (C-1929, C-1930). One call, no fourth copy of the test.
        in_japanese = _reply_in_japanese(message)
        if verdict["valid"]:
            # C-1932: in an English reply a shape's own key IS its English
            # name (fish / boat / terrain), so no second table is written.
            shape_label = (
                SHAPE_LABELS.get(model.shape, model.shape)
                if in_japanese
                else model.shape
            )
            summary = (
                (
                    f"「{model.title}」の 3D モデルを作りました"
                    f"（形状: {shape_label}、low-poly、頂点 {verdict['vertices']}・"
                    f"面 {verdict['faces']}）。"
                    ".obj は Windows の 3D ビューアーでそのまま開けます。"
                    "プレビュー HTML はブラウザで回転表示できます。"
                    # C-1617: the .obj's colours resolve only from the
                    # companion .mtl, so say to keep them together.
                    "色（配色）は隣に保存された .mtl から付くので、"
                    ".obj と一緒に置いてください。"
                )
                if in_japanese
                else (
                    f"Made a 3D model for \u201c{model.title}\u201d "
                    f"(shape: {shape_label}, low-poly, {verdict['vertices']} "
                    f"vertices, {verdict['faces']} faces). "
                    "The .obj opens directly in the Windows 3D viewer, and the "
                    "preview HTML turns it in a browser. "
                    "The colours come from the .mtl saved beside it, so keep "
                    "the .obj and the .mtl together."
                )
            )
            # The request named no shape, so the default was used (C-1267).
            if not model.shape_named:
                choices = (
                    " / ".join(SHAPE_LABELS.values())
                    if in_japanese
                    else " / ".join(SHAPE_LABELS)
                )
                summary += (
                    (
                        f"依頼に合う形状が無かったので、既定の"
                        f"「{SHAPE_LABELS[DEFAULT_SHAPE]}」にしました。"
                        f"いま作れる形状は {choices} です。"
                    )
                    if in_japanese
                    else (
                        " No shape in the request matched one that can be made, "
                        f"so the default \u201c{DEFAULT_SHAPE}\u201d was used. "
                        f"The shapes you can ask for are {choices}."
                    )
                )
            # The colour was not applied (C-1272).
            if names_color(message):
                summary += (
                    (
                        "依頼にあった色は今の配色に反映していません。"
                        "3D モデルは固定の配色で描いています。"
                    )
                    if in_japanese
                    else (
                        " The colour in the request is not applied. The model is "
                        "painted in a fixed palette."
                    )
                )
            # C-1832: and the count, from the same source as the preview's note.
            summary += count_note(message, in_japanese=in_japanese)
        else:
            summary = (
                (
                    f"「{model.title}」の 3D モデルを作りましたが、検証に落ちています: "
                    + "、".join(str(f) for f in verdict["failures"])
                )
                if in_japanese
                else (
                    f"Made a 3D model for \u201c{model.title}\u201d, but it "
                    "fails validation: "
                    + ", ".join(str(f) for f in verdict["failures"])
                )
            )
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(paths["preview"]),
            details={
                "title": model.title,  # C-1830
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
