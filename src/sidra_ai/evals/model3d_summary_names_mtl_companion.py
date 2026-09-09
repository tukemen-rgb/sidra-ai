"""Does the 3D summary tell the reader the colours live in the companion .mtl?

C-1617. A generated model is three files - model3d-<shape>-<stamp>.obj, its
.mtl, and a preview - and the .obj's colours (the GAMEYARD palette, its whole
visual identity) resolve only from the .mtl sitting beside it (`usemtl gy_cyan`
is defined in the .mtl, referenced by `mtllib`). The summary named the .obj and
the preview and said 「.obj は…そのまま開けます」, which reads as self-sufficient,
but never mentioned the .mtl. A non-expert who opens the .obj alone gets a
silently colourless model.

The summary now says the colours come from the companion .mtl and to keep the
two together. The default-shape disclosure (C-1267), the colour-not-applied note
(C-1272), the vertex/face counts, and the obj/preview guidance are unchanged.

Measured through the real chat path: the summary is the answer a user reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_MTL = ".mtl"
#: A distinctive phrase from the companion clause: keep the .obj and .mtl
#: together. Chosen so the colour-not-applied note ("依頼にあった色は…") cannot
#: satisfy this check by itself.
_COMPANION = "一緒に置いて"

_DEFAULT_NOTE = "依頼に合う形状が無かったので"
_COLOR_NOT_APPLIED = "依頼にあった色は今の配色に反映していません"


@dataclass(frozen=True)
class Model3dMtlCompanionResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="m3d-mtl-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def _answer(service, request: str) -> str:
    return str((service.chat(request) or {}).get("answer") or "")


def evaluate_model3d_summary_names_mtl_companion() -> Model3dMtlCompanionResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    fish = _answer(service, "魚の3Dモデルを作って")
    # --- the companion clause is present, and on a named shape too ---
    add(_MTL in fish, "named-shape summary does not mention the .mtl")
    add(_COMPANION in fish,
        "named-shape summary does not say to keep .obj and .mtl together")
    # --- non-regression of the existing summary content ---
    add("頂点" in fish and "面" in fish, "vertex/face counts went missing")
    add(".obj" in fish, "the .obj guidance went missing")
    add("プレビュー" in fish, "the preview guidance went missing")
    add(_DEFAULT_NOTE not in fish, "a named shape wrongly got the default note")

    dragon = _answer(service, "ドラゴンの3Dモデルを作って")
    # --- the companion clause is on the default-shape path too ---
    add(_MTL in dragon and _COMPANION in dragon,
        "default-shape summary lost the .mtl companion clause")
    add(_DEFAULT_NOTE in dragon, "the default-shape disclosure was lost")
    add("いま作れる形状は" in dragon, "the shape choices were lost")

    colored = _answer(service, "青い魚の3Dモデルを作って")
    add(_COLOR_NOT_APPLIED in colored and _MTL in colored,
        "colour-not-applied note or .mtl clause lost when a colour is named")

    total = 10
    return Model3dMtlCompanionResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "Model3dMtlCompanionResult",
    "evaluate_model3d_summary_names_mtl_companion",
]
