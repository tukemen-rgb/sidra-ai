"""Do the GIF and 3D generators admit they did not apply a requested colour?

C-1272: C-1271 gave the art generator an honest note when a request named a
colour the fixed brand palette could not honour. The GIF and 3D generators had
the same gap - 「青いGIFを作って」 drew the usual palette and the summary quoted
「青い」 back with no word that the colour was ignored; 「青い3Dモデルを作って」 did
the same with the low-poly palette. Both now carry the note when a colour is
named, and none when it is not. The palettes themselves are unchanged.

Measured through the real chat path, over both kinds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: (request, kind) pairs that name a colour: each summary must carry the note.
_COLORED: tuple[tuple[str, str], ...] = (
    ("青いGIFを作って", "gif"),
    ("赤いアニメGIFを作って", "gif"),
    ("緑の魚のGIFを作って", "gif"),
    ("青い3Dモデルを作って", "model3d"),
    ("赤い魚の3Dモデルを作って", "model3d"),
)

#: Requests naming no colour: no colour note is due.
_UNCOLORED: tuple[tuple[str, str], ...] = (
    ("魚のGIFを作って", "gif"),
    ("GIFを作って", "gif"),
    ("魚の3Dモデルを作って", "model3d"),
    ("3Dモデルを作って", "model3d"),
)

_NOTE_MARKER = "色は今の配色に反映していません"


@dataclass(frozen=True)
class GifModel3dColorHonestResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="gif3d-color-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def _answer_of(service, request: str, kind: str) -> tuple[str, bool]:
    result = service.chat(request) or {}
    creation = result.get("creation") or {}
    outcome = creation.get("outcome") or {}
    got_kind = (creation.get("intent") or {}).get("kind")
    handled = bool(outcome.get("handled")) and got_kind == kind
    return str(result.get("answer") or ""), handled


def evaluate_gif_3d_color_named_honest() -> GifModel3dColorHonestResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request, kind in _COLORED:
        answer, handled = _answer_of(service, request, kind)
        if not handled:
            failures.append(f"{request!r}: did not route to {kind}")
            continue
        add(_NOTE_MARKER in answer, f"{request!r}: no colour note in 「{answer}」")

    for request, kind in _UNCOLORED:
        answer, handled = _answer_of(service, request, kind)
        if not handled:
            failures.append(f"{request!r}: did not route to {kind}")
            continue
        add(_NOTE_MARKER not in answer,
            f"{request!r}: got a colour note though no colour was named: 「{answer}」")

    total = len(_COLORED) + len(_UNCOLORED)
    return GifModel3dColorHonestResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["GifModel3dColorHonestResult", "evaluate_gif_3d_color_named_honest"]
