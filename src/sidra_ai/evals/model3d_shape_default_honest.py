"""Does a 3D model name its shape, and say when it fell back to the default?

C-1267: the 3D generator ships three shapes (fish/boat/terrain) chosen by
keyword; anything else silently becomes the fish mesh, and the summary named no
shape - 「猫の3Dモデルを作って」 → 「『猫』の 3D モデルを作りました（low-poly …）」,
a fish, with no word about the shape. Art (C-1256) and GIF (C-1258) were fixed
the same way; 3D is the third generator with the gap, and like GIF it did not
even print the shape.

The summary now names the shape, and when the request matched no shape word it
says the default was used and lists the shapes that can be asked for. It is not
a claim the subject cannot be modelled - the shapes are abstract - only that the
default was used and what can be picked.

Measured through the real chat path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Requests naming no shape word: each builds the default and must say so.
_UNNAMED: tuple[str, ...] = (
    "猫の3Dモデルを作って",
    "ドラゴンの3Dモデルを作って",
    "3Dモデルを作って",
)

#: Requests naming a shape (fish/boat/terrain words): no default note is due.
_NAMED: tuple[str, ...] = (
    "魚の3Dモデルを作って",
    "船の3Dモデルを作って",
)

_NOTE_MARKER = "依頼に合う形状が無かったので"
_SHAPE_LABEL = "形状"
#: The other two shapes the note must offer (fish is the drawn default, so it
#: appears anyway; 舟/地形 only appear when the choices are actually listed).
_CHOICE_MARKERS = ("舟", "地形")


@dataclass(frozen=True)
class Model3dShapeDefaultHonestResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="m3d-shape-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def _answer_of(service, request: str) -> tuple[str, bool]:
    result = service.chat(request) or {}
    creation = result.get("creation") or {}
    outcome = creation.get("outcome") or {}
    kind = (creation.get("intent") or {}).get("kind")
    handled = bool(outcome.get("handled")) and kind == "model3d"
    return str(result.get("answer") or ""), handled


def evaluate_model3d_shape_default_honest() -> Model3dShapeDefaultHonestResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request in _UNNAMED + _NAMED:
        answer, handled = _answer_of(service, request)
        if not handled:
            failures.append(f"{request!r}: did not route to model3d")
            continue
        # 1 (all): the summary names the shape it built.
        add(_SHAPE_LABEL in answer, f"{request!r}: shape not named in 「{answer}」")

    for request in _UNNAMED:
        answer, handled = _answer_of(service, request)
        if not handled:
            failures.append(f"{request!r}: (no note - not routed)")
            failures.append(f"{request!r}: (no choices - not routed)")
            continue
        # 2: the default note is present.
        add(_NOTE_MARKER in answer, f"{request!r}: no default note in 「{answer}」")
        # 3: ...and it lists the shapes that can be asked for.
        add(all(m in answer for m in _CHOICE_MARKERS),
            f"{request!r}: default note omits choices {_CHOICE_MARKERS} in 「{answer}」")

    for request in _NAMED:
        answer, handled = _answer_of(service, request)
        if not handled:
            failures.append(f"{request!r}: (note-absent check skipped - not routed)")
            continue
        # 4: a named shape draws no default note.
        add(_NOTE_MARKER not in answer,
            f"{request!r}: got a default note though a shape was named: 「{answer}」")

    total = len(_UNNAMED + _NAMED) + 2 * len(_UNNAMED) + len(_NAMED)
    return Model3dShapeDefaultHonestResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "Model3dShapeDefaultHonestResult",
    "evaluate_model3d_shape_default_honest",
]
