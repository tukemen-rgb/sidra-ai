"""The GIF generator as the router sees it.

Same split as every other kind: :mod:`sidra_ai.creation.gifs` knows bytes
and nothing about HTTP, this file holds the one callable the router needs.
The summary reports what the validator found in the actual bytes, not the
fact that a file was written.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.gifs import generate_gif, save_gif, validate_gif
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
        if verdict["valid"]:
            summary = (
                f"「{gif.title}」のアニメ GIF を作りました"
                f"（{verdict['frames']} フレーム・{verdict['width']}×{verdict['height']}・ループ再生）。"
                "生成ファイル一覧からダウンロードして、ブラウザや画像ビューアーで開けます。"
            )
        else:
            summary = (
                f"「{gif.title}」の GIF を作りましたが、検証に落ちています: "
                + "、".join(str(f) for f in verdict["failures"])
            )
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(path),
            details={
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
