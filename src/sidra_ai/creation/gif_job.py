"""The GIF generator as the router sees it.

Same split as every other kind: :mod:`sidra_ai.creation.gifs` knows bytes
and nothing about HTTP, this file holds the one callable the router needs.
The summary reports what the validator found in the actual bytes, not the
fact that a file was written.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.models.echo import _reply_in_japanese

from sidra_ai.creation.art import names_color
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.gifs import (
    DEFAULT_MOTIF,
    MOTIF_LABELS,
    generate_gif,
    length_note,
    save_gif,
    validate_gif,
)
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.router import CreationOutcome


def build_gif_generator(data_dir: str | Path):
    def generate(
        message: str,
        intent: CreationIntent,
        retrieved: list[Fact] | None = None,
    ) -> CreationOutcome:
        evidence = [fact.source for fact in (retrieved or []) if fact.source]
        gif = generate_gif(message, evidence=evidence or None)
        verdict = validate_gif(gif)
        path = save_gif(gif, data_dir)
        # C-1932: the product's own rule for which language the reply
        # takes (C-1929, C-1930). One call, no third copy of the test.
        in_japanese = _reply_in_japanese(message)
        if verdict["valid"]:
            # C-1932: in an English reply a motif's own key IS its English
            # name (fish / pulse), so no second table is written.
            motif_label = (
                MOTIF_LABELS.get(gif.motif, gif.motif) if in_japanese else gif.motif
            )
            summary = (
                (
                    f"「{gif.title}」のアニメ GIF を作りました"
                    f"（絵柄: {motif_label}・{verdict['frames']} フレーム・"
                    f"{verdict['width']}×{verdict['height']}・ループ再生）。"
                    "ブラウザや画像ビューアーで開けます。"
                )
                if in_japanese
                else (
                    f"Made an animated GIF for \u201c{gif.title}\u201d "
                    f"(motif: {motif_label}, {verdict['frames']} frames, "
                    f"{verdict['width']}x{verdict['height']}, loops). "
                    "Open it in a browser or an image viewer."
                )
            )
            # The request named no motif, so the default was used (C-1258).
            if not gif.motif_named:
                # C-1850: built from MOTIF_LABELS, not written out, so a third
                # motif joins the sentence by existing.
                choices = (
                    " / ".join(MOTIF_LABELS.values())
                    if in_japanese
                    else " / ".join(MOTIF_LABELS)
                )
                summary += (
                    (
                        f"依頼に合う絵柄が無かったので、既定の"
                        f"「{MOTIF_LABELS[DEFAULT_MOTIF]}」にしました。"
                        f"いま絵柄を指定できるのは {choices} です。"
                    )
                    if in_japanese
                    else (
                        " No motif in the request matched one that can be drawn, "
                        f"so the default \u201c{DEFAULT_MOTIF}\u201d was used. "
                        f"The motifs you can ask for are {choices}."
                    )
                )
            # The colour was not applied (C-1272).
            if names_color(message):
                summary += (
                    (
                        "依頼にあった色は今の配色に反映していません。"
                        "GIF は固定の配色で描いています。"
                    )
                    if in_japanese
                    else (
                        " The colour in the request is not applied. The GIF is "
                        "drawn in a fixed palette."
                    )
                )
            # C-1823: and the length, from the validated bytes.
            summary += length_note(
                message, verdict["frames"], in_japanese=in_japanese
            )
        else:
            summary = (
                (
                    f"「{gif.title}」の GIF を作りましたが、検証に落ちています: "
                    + "、".join(str(f) for f in verdict["failures"])
                )
                if in_japanese
                else (
                    f"Made a GIF for \u201c{gif.title}\u201d, but it fails "
                    "validation: "
                    + ", ".join(str(f) for f in verdict["failures"])
                )
            )
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(path),
            details={
                "title": gif.title,  # C-1830
                "motif": gif.motif,
                "seed": gif.seed,
                "valid": verdict["valid"],
                "frames": verdict["frames"],
                "bytes": verdict["bytes"],
                "looped": verdict["looped"],
            },
        )

    return generate


__all__ = ["build_gif_generator"]
