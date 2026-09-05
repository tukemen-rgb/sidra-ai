"""Does a GIF name its motif, and say when it fell back to the default?

C-1258: the GIF generator ships two motifs - ``fish`` and the default
``pulse`` (concentric rings) - and the summary named neither. 「猫のGIFを
作って」 came back 「『猫』のアニメ GIF を作りました（10 フレーム・120×90・
ループ再生）」: concentric rings, titled 猫, with no word about the motif and
no sign the subject was not drawn. Art was made to at least print 「パターン:
flow」 and to say so when it defaulted (C-1256); the GIF summary did not name
the motif at all, so it hid even more.

The fix names the motif in every summary, and when the request matched no
motif word it says the default was used and names the one motif that can be
asked for (魚). It is not a claim the subject cannot be drawn - the motifs
are abstract - only that the default was used and what can be picked.

Measured through the real ``chat`` path: the note lives in the summary a user
reads, and a probe that re-derived the routing would stay green while the
product stayed silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Requests naming no motif word: each draws the default and must say so.
_UNNAMED: tuple[str, ...] = (
    "猫のGIFを作って",
    "星のGIFを作って",
    "GIFを作って",
)

#: Requests naming a motif (fish words): no default note is due.
_NAMED: tuple[str, ...] = (
    "魚のGIFを作って",
    "釣りのGIFを作って",
)

#: The marker only the default note carries.
_NOTE_MARKER = "依頼に合う絵柄が無かったので"

#: Every summary must name the motif it drew. 「絵柄:」 is the label the fix
#: adds; before it the summary named no motif at all.
_MOTIF_LABEL = "絵柄"

#: The one motif a user can actually ask for, which the default note must
#: offer so a reader who got the default knows what to type next.
_REQUESTABLE_MOTIF = "魚"


@dataclass(frozen=True)
class GifMotifDefaultHonestResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    """A real service, echo backend, empty corpus (GIFs need no evidence)."""

    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="gif-motif-"))
    settings = Settings(data_dir=str(tmp / "sidra"))
    return SidraService(settings)


def _answer_of(service, request: str) -> tuple[str, bool]:
    result = service.chat(request) or {}
    creation = result.get("creation") or {}
    outcome = creation.get("outcome") or {}
    kind = (creation.get("intent") or {}).get("kind")
    handled = bool(outcome.get("handled")) and kind == "gif"
    return str(result.get("answer") or ""), handled


def evaluate_gif_motif_default_honest() -> GifMotifDefaultHonestResult:
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
            failures.append(f"{request!r}: did not route to gif")
            continue
        # 1 (all): the summary names the motif it drew.
        add(_MOTIF_LABEL in answer,
            f"{request!r}: motif not named in 「{answer}」")

    for request in _UNNAMED:
        answer, handled = _answer_of(service, request)
        if not handled:
            failures.append(f"{request!r}: (no note - not routed)")
            failures.append(f"{request!r}: (no choice - not routed)")
            continue
        # 2: the default note is present.
        add(_NOTE_MARKER in answer,
            f"{request!r}: no default note in 「{answer}」")
        # 3: ...and it names the motif that can be asked for.
        add(_REQUESTABLE_MOTIF in answer,
            f"{request!r}: default note omits 「{_REQUESTABLE_MOTIF}」 in 「{answer}」")

    for request in _NAMED:
        answer, handled = _answer_of(service, request)
        if not handled:
            failures.append(f"{request!r}: (note-absent check skipped - not routed)")
            continue
        # 4: a named motif draws no default note.
        add(_NOTE_MARKER not in answer,
            f"{request!r}: got a default note though a motif was named: 「{answer}」")

    total = len(_UNNAMED + _NAMED) + 2 * len(_UNNAMED) + len(_NAMED)
    return GifMotifDefaultHonestResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "GifMotifDefaultHonestResult",
    "evaluate_gif_motif_default_honest",
]
