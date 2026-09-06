"""Does the art generator admit it did not apply a requested colour?

C-1271: the art palette is fixed to the GAMEYARD brand (cyan on dark) by design.
A request naming a colour - 「青い海のアート」「赤い炎のアート」「緑の森のアート」 -
was drawn in the very same cyan-and-pink as every other art, and the summary
named only the pattern, never that the colour had been ignored. The title even
quoted the colour back (「青い海」のジェネラティブアート), reading as though it had
been honoured.

The fix is the same honesty the pattern default note gives (C-1256): when the
request names a colour, the summary says the colour was not applied and that the
art uses the fixed brand palette. Colour is not a selectable option here, so it
states the fixed palette rather than offering choices. Requests that name no
colour draw no such note.

Measured through the real chat path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Requests that name a colour: each must carry the honesty note.
_COLORED: tuple[str, ...] = (
    "青い海のアートを作って",
    "赤い炎のアートを作って",
    "緑の森のアートを作って",
    "ブルーの抽象アートを作って",
)

#: Requests that name no colour: no colour note is due.
_UNCOLORED: tuple[str, ...] = (
    "フローのアートを作って",
    "軌道のアートを作って",
    "アートを作って",
)

_NOTE_MARKER = "色は今の配色に反映していません"
#: The fixed palette the note must name, so "note present" also proves it told
#: the reader what they got instead.
_PALETTE_MARKER = "シアン"


@dataclass(frozen=True)
class ArtColorNamedHonestResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="art-color-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def _answer_of(service, request: str) -> tuple[str, bool]:
    result = service.chat(request) or {}
    creation = result.get("creation") or {}
    outcome = creation.get("outcome") or {}
    kind = (creation.get("intent") or {}).get("kind")
    handled = bool(outcome.get("handled")) and kind == "art"
    return str(result.get("answer") or ""), handled


def evaluate_art_color_named_honest() -> ArtColorNamedHonestResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request in _COLORED:
        answer, handled = _answer_of(service, request)
        if not handled:
            failures.append(f"{request!r}: did not route to art")
            failures.append(f"{request!r}: (palette marker skipped - not routed)")
            continue
        # 1: the summary admits the colour was not applied.
        add(_NOTE_MARKER in answer, f"{request!r}: no colour note in 「{answer}」")
        # 2: ...and names the fixed palette the reader actually got.
        add(_PALETTE_MARKER in answer,
            f"{request!r}: colour note does not name the palette in 「{answer}」")

    for request in _UNCOLORED:
        answer, handled = _answer_of(service, request)
        if not handled:
            failures.append(f"{request!r}: did not route to art")
            continue
        # 3: a request naming no colour draws no colour note.
        add(_NOTE_MARKER not in answer,
            f"{request!r}: got a colour note though no colour was named: 「{answer}」")

    total = 2 * len(_COLORED) + len(_UNCOLORED)
    return ArtColorNamedHonestResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ArtColorNamedHonestResult", "evaluate_art_color_named_honest"]
