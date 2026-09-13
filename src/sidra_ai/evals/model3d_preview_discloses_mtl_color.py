"""Does the 3D preview page itself warn that colour comes from the .mtl?

C-1784. ``model3d_job`` returns the preview HTML as the primary artifact, so the
page is what a user reopens later or forwards to a colleague. The preview renders
a fully coloured model, and its note said only 「.obj は Windows の 3D ビューアー
で開けます」. But the .obj's colours resolve only from the sibling .mtl (via
mtllib); opening the .obj alone yields a grey model. C-1617 added that caveat -
but only to the chat summary, while C-1283 established that the preview page must
carry its own disclosures. So a user holding just the preview followed the page's
advice, opened the .obj, and lost every colour it showed.

The preview note now carries the .mtl colour caveat too. The checks read the
real ``generate_model3d`` preview HTML and the ``model3d_job`` chat summary.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.creation.model3d_job import build_model3d_generator
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.scratch import scratch_dir


@dataclass(frozen=True)
class Model3dPreviewMtlResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_model3d_preview_discloses_mtl_color() -> Model3dPreviewMtlResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A request that names no shape (the default-fish path, still fully supported)
    unshaped = generate_model3d("3Dモデルを作って").preview_html
    # A request whose shape is explicitly named (no shape-default note)
    shaped = generate_model3d("魚の3Dモデルを作って", shape="fish").preview_html

    # --- (A) the preview page names the .mtl -----------------------------
    add(".mtl" in unshaped, "A: the preview page never mentions the .mtl")
    # --- (B) ...and ties colour to keeping it beside the .obj ------------
    add("色" in unshaped and ".mtl" in unshaped and ("隣" in unshaped or "一緒" in unshaped),
        "B: the preview page does not tie colour to the .mtl companion")
    # --- (C) the advice to open the .obj still stands --------------------
    add("開けます" in unshaped, "C: the preview page lost the 'open the .obj' guidance")
    # --- (D) the C-1283 shape-default note still fires when unshaped -----
    add("既定" in unshaped, "D: the shape-default disclosure (C-1283) regressed")
    # --- (E) the chat summary still carries the .mtl caveat (C-1617) -----
    # Through the shared helper, not tempfile directly (C-1770): a judge that
    # makes its own scratch and never removes it is what filled this
    # container's disk, and a full disk makes the collector die partway and
    # report the metrics it never reached as REGRESSED. scratch_dir
    # registers the directory for removal at interpreter exit.
    gen = build_model3d_generator(scratch_dir())
    outcome = gen("3Dモデルを作って", detect_creation_intent("3Dモデルを作って"))
    summary = getattr(outcome, "summary", "") or ""
    add(".mtl" in summary and ("隣" in summary or "一緒" in summary),
        "E: the chat summary lost its .mtl caveat")
    # --- (F) the .mtl note is present even when a shape was named --------
    #         (colour comes from the .mtl regardless of shape)
    add(".mtl" in shaped and "既定" not in shaped,
        "F: a named-shape preview dropped the .mtl note or wrongly showed the default note")

    total = 6
    return Model3dPreviewMtlResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "Model3dPreviewMtlResult",
    "evaluate_model3d_preview_discloses_mtl_color",
]
