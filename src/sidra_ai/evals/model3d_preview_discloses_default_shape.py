"""Does the 3D preview page disclose the fish default it fell back to?

C-1283: a request that names no shape (「ドラゴンの 3D モデル」) is built as the
fish default. The chat summary says so (C-1267), but the preview HTML is the
artifact opened in a browser and forwarded, and it was titled 「ドラゴン」 over a
fish mesh with no word of it - the same silent artifact C-1281 fixed for the
report. The preview now carries a disclosure note under the title whenever the
shape was a default, and stays clean when a shape was named.

Drives the router's model3d generator for the saved file and ``generate_model3d``
for the property, over a request that falls back and requests that name a shape.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

_NOTE_MARK = '<p id="shape-note">'
_SHAPES = ("魚", "舟", "地形")


@dataclass(frozen=True)
class Model3DPreviewResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _router_preview(request: str) -> str:
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.router import build_default_router

    tmp = tempfile.mkdtemp(prefix="m3d-preview-")
    router = build_default_router(data_dir=tmp)
    out = router.route(request, detect_creation_intent(request), [])
    return Path(out.artifact_path).read_text(encoding="utf-8")


def evaluate_model3d_preview_discloses_default_shape() -> Model3DPreviewResult:
    from sidra_ai.creation.models3d import generate_model3d, validate_model3d

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1: the saved preview for a no-shape request discloses the fish default,
    #    names the shapes that can be asked for, and still keeps the subject as
    #    the title (both the user's word and the real shape are visible).
    html = _router_preview("ドラゴンの 3D モデルを作って")
    add(_NOTE_MARK in html, "fallback preview has no disclosure note element")
    add("既定の「魚」" in html, "fallback preview does not name the fish default")
    add(all(s in html for s in _SHAPES), "fallback preview omits the shape choices")
    add("<h1>ドラゴン</h1>" in html, "fallback preview dropped the subject title")

    # 2: a named shape gets no note, in the model and through the router.
    for req, shape in (("魚の 3D モデルを作って", "fish"),
                       ("舟の 3D モデルを作って", "boat"),
                       ("地形の 3D モデルを作って", "terrain")):
        model = generate_model3d(req)
        add(model.shape == shape and model.shape_named
            and _NOTE_MARK not in model.preview_html,
            f"named shape {shape!r} preview should carry no note")

    # 3: the note carries no fabricated figure - a digit on a slide/page that
    #    names nothing retrieved is exactly what the generators must not print.
    #    Guarded so pre-fix code (no note at all) scores a failure, not a crash.
    fallback = generate_model3d("猫の 3D モデルを作って")
    if _NOTE_MARK in fallback.preview_html:
        note = fallback.preview_html.split(_NOTE_MARK, 1)[1].split("</p>", 1)[0]
        add(not any(ch.isdigit() for ch in note),
            f"disclosure note carries a digit: {note!r}")
    else:
        failures.append("fallback preview has no note to check for a digit")

    # 4: the disclosure does not break the preview - it still passes the same
    #    validator (canvas, script, reduced-motion, no external asset).
    add(validate_model3d(fallback)["valid"], "disclosure made the preview invalid")

    total = 4 + 3 + 1 + 1
    return Model3DPreviewResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "Model3DPreviewResult",
    "evaluate_model3d_preview_discloses_default_shape",
]
