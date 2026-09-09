"""The art generator as the router sees it.

Same split as every other kind: :mod:`sidra_ai.creation.art` knows canvases
and seeds, this file holds the one callable the router needs, and the
summary reports the validator's verdict rather than the write.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.creation.art import (
    DEFAULT_PATTERN,
    PATTERN_LABELS,
    PATTERNS,
    generate_art,
    names_color,
    save_art,
    validate_art,
)
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.router import CreationOutcome


def build_art_generator(data_dir: str | Path):
    def generate(
        message: str,
        intent: CreationIntent,
        retrieved: list[Fact] | None = None,
    ) -> CreationOutcome:
        evidence = [fact.source for fact in (retrieved or []) if fact.source]
        art = generate_art(message, evidence=evidence or None)
        verdict = validate_art(art)
        path = save_art(art, data_dir)
        if verdict["valid"]:
            summary = (
                f"「{art.title}」のジェネラティブアートを作りました"
                # C-1619: the Japanese label, not the internal key - 3D/GIF and
                # this summary's own default note already read フロー/軌道, so
                # 「パターン: flow」 leaked the key and clashed with 「既定の『フロー』」
                # in one reply (C-1259, one generator along).
                f"（パターン: {PATTERN_LABELS.get(art.pattern, art.pattern)}、seed {art.seed}）。"
                "HTML をブラウザで開くとその場で描画され、同じ依頼なら同じ絵になります。"
            )
            # The request named no pattern, so the default was used. Say so and
            # name the choices - a reader who asked for 「螺旋」 got a flow field
            # and would otherwise never learn there were two patterns to pick
            # from (C-1256). Not a claim the subject can't be drawn: the two
            # patterns are abstract, so the honest fact is just "you didn't
            # pick, here is what you got and what you could pick".
            if not art.pattern_named:
                choices = " / ".join(PATTERN_LABELS[name] for name in PATTERNS)
                summary += (
                    f"依頼にパターン名が無かったので、既定の"
                    f"「{PATTERN_LABELS[DEFAULT_PATTERN]}」で描きました。"
                    f"指定できるパターンは {choices} です。"
                )
            # The request named a colour, but the palette is fixed to the brand
            # (cyan on dark), so 「青い海」 was drawn cyan and pink. Say the colour
            # was not applied rather than let the title imply it was - the same
            # honesty the pattern default note gives (C-1271). Colour is not a
            # choice here, so this states the fixed palette instead of offering
            # options.
            if names_color(message):
                summary += (
                    "依頼にあった色は今の配色に反映していません。"
                    "アートはブランド固定の配色（シアン×マゼンタ）で描いています。"
                )
        else:
            summary = (
                f"「{art.title}」のアートを作りましたが、検証に落ちています: "
                + "、".join(str(f) for f in verdict["failures"])
            )
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(path),
            details={
                "pattern": art.pattern,
                "seed": art.seed,
                "valid": verdict["valid"],
                "js_checker": verdict["js_checker"],
                "bytes": verdict["bytes"],
            },
        )

    return generate


__all__ = ["build_art_generator"]
