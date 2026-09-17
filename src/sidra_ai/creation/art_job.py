"""The art generator as the router sees it.

Same split as every other kind: :mod:`sidra_ai.creation.art` knows canvases
and seeds, this file holds the one callable the router needs, and the
summary reports the validator's verdict rather than the write.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.models.echo import _reply_in_japanese

from sidra_ai.creation.art import (
    DEFAULT_PATTERN,
    PATTERN_LABELS,
    PATTERNS,
    generate_art,
    names_color,
    subject_of,
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
        # C-1932: which language this reply takes, from the product's own
        # rule (`_reply_in_japanese`, as C-1929 and C-1930 use it). No third
        # copy of the language test - a copied rule is the copy that drifts.
        in_japanese = _reply_in_japanese(message)
        if verdict["valid"]:
            # C-1932: in an English reply a pattern's own key IS its English
            # name (flow / orbits). C-1619 chose the Japanese label over the
            # key so a Japanese reply would not leak an internal word; that
            # reasoning is about the Japanese reply, and in the English one
            # the key is simply the right word. No second table either.
            pattern_name = (
                PATTERN_LABELS.get(art.pattern, art.pattern)
                if in_japanese
                else art.pattern
            )
            summary = (
                (
                    f"「{art.title}」のジェネラティブアートを作りました"
                    f"（パターン: {pattern_name}、seed {art.seed}）。"
                    "HTML をブラウザで開くとその場で描画され、"
                    "同じ依頼なら同じ絵になります。"
                )
                if in_japanese
                else (
                    f"Made generative art for \u201c{art.title}\u201d "
                    f"(pattern: {pattern_name}, seed {art.seed}). "
                    "Open the HTML in a browser and it draws itself; the same "
                    "request gives the same picture."
                )
            )
            # The request named no pattern, so the default was used. Say so and
            # name the choices - a reader who asked for 「螺旋」 got a flow field
            # and would otherwise never learn there were two patterns to pick
            # from (C-1256).
            if not art.pattern_named:
                choices = (
                    " / ".join(PATTERN_LABELS[name] for name in PATTERNS)
                    if in_japanese
                    else " / ".join(PATTERNS)
                )
                summary += (
                    (
                        f"依頼にパターン名が無かったので、既定の"
                        f"「{PATTERN_LABELS[DEFAULT_PATTERN]}」で描きました。"
                        f"指定できるパターンは {choices} です。"
                    )
                    if in_japanese
                    else (
                        " The request named no pattern, so it was drawn with the "
                        f"default \u201c{DEFAULT_PATTERN}\u201d. "
                        f"The patterns you can ask for are {choices}."
                    )
                )
            # C-1806: the patterns depict nothing, so a request that named a
            # subject must hear that the subject was not drawn.
            if subject_of(message):
                kinds = (
                    " / ".join(PATTERN_LABELS.values())
                    if in_japanese
                    else " / ".join(PATTERNS)
                )
                summary += (
                    (
                        "依頼にあった題材は描いていません。"
                        f"アートは抽象の模様（{kinds}）です。"
                    )
                    if in_japanese
                    else (
                        " The subject in the request is not drawn. The art is an "
                        f"abstract pattern ({kinds})."
                    )
                )
            if names_color(message):
                summary += (
                    (
                        "依頼にあった色は今の配色に反映していません。"
                        "アートはブランド固定の配色（シアン×マゼンタ）で描いています。"
                    )
                    if in_japanese
                    else (
                        " The colour in the request is not applied. The art is "
                        "drawn in the fixed brand palette (cyan and magenta)."
                    )
                )
        else:
            summary = (
                (
                    f"「{art.title}」のアートを作りましたが、検証に落ちています: "
                    + "、".join(str(f) for f in verdict["failures"])
                )
                if in_japanese
                else (
                    f"Made art for \u201c{art.title}\u201d, but it fails "
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
                "title": art.title,  # C-1830
                "pattern": art.pattern,
                "seed": art.seed,
                "valid": verdict["valid"],
                "js_checker": verdict["js_checker"],
                "bytes": verdict["bytes"],
            },
        )

    return generate


__all__ = ["build_art_generator"]
