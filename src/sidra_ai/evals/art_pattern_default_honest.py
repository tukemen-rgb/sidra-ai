"""When art falls back to the default pattern, is the user told?

C-1256: generative art ships two patterns (``flow``/``orbits``) chosen by
keyword, and any request that names neither silently becomes ``flow``.
「螺旋のアートを作って」 came back 「『螺旋のアート』のジェネラティブアートを
作りました（パターン: flow、seed …）」 - a flow field, while the reader asked
for a spiral and is told neither that only two patterns exist nor that their
words matched neither and fell to the default. Games decline an unsupported
request honestly and list what they can make (C-1121/C-1125/C-1240/C-1253);
art alone went quiet.

The fix is the honest note, not a claim the subject cannot be drawn: the two
patterns are abstract, so overclaiming 「螺旋は描けない」 would be its own lie.
When no pattern word matched, the summary says the default was used and names
the choices; when a pattern *was* named (フロー/軌道/円…), it stays silent.

Measured through the real ``chat`` path, because the note lives in the
summary a user actually reads, and a probe that re-derived the routing would
stay green while the product went quiet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Requests that name no pattern word: each must draw the default and say so.
_UNNAMED: tuple[str, ...] = (
    "螺旋のアートを作って",
    "点描のアートを作って",
    "幾何学模様のアートを作って",
    "アートを作って",
)

#: Requests that name a pattern (flow words / orbit words): no note is due.
_NAMED: tuple[str, ...] = (
    "フローアートを作って",
    "軌道のアートを作って",
    "円のアートを作って",
)

#: The marker only the default note carries. Kept apart from the choice names
#: so "note present" and "choices listed" are two independent checks - a note
#: that forgot to list what you can pick still fails the second.
_NOTE_MARKER = "パターン名が無かったので"

#: Both pattern display names the note must offer. 「フロー」 also appears in
#: 「既定の「フロー」」, so requiring 「軌道」 as well is what actually proves the
#: choices were listed rather than just the default named.
_CHOICE_NAMES: tuple[str, ...] = ("フロー", "軌道")


@dataclass(frozen=True)
class ArtPatternDefaultHonestResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    """A real service, echo backend, empty corpus (art needs no evidence)."""

    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="art-honest-"))
    settings = Settings(data_dir=str(tmp / "sidra"))
    return SidraService(settings)


def _answer_of(service, request: str) -> tuple[str, bool]:
    result = service.chat(request) or {}
    creation = result.get("creation") or {}
    outcome = creation.get("outcome") or {}
    kind = (creation.get("intent") or {}).get("kind")
    handled = bool(outcome.get("handled")) and kind == "art"
    return str(result.get("answer") or ""), handled


def evaluate_art_pattern_default_honest() -> ArtPatternDefaultHonestResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request in _UNNAMED:
        answer, handled = _answer_of(service, request)
        if not handled:
            failures.append(f"{request!r}: did not route to art")
            failures.append(f"{request!r}: (no note - not routed)")
            continue
        # 1: the summary carries the default note.
        add(_NOTE_MARKER in answer,
            f"{request!r}: no default note in 「{answer}」")
        # 2: ...and the note lists both patterns the user could have picked.
        add(all(name in answer for name in _CHOICE_NAMES),
            f"{request!r}: note omits a choice ({_CHOICE_NAMES}) in 「{answer}」")

    for request in _NAMED:
        answer, handled = _answer_of(service, request)
        if not handled:
            failures.append(f"{request!r}: did not route to art")
            continue
        # 3: a named pattern draws no note - the request said what it wanted.
        add(_NOTE_MARKER not in answer,
            f"{request!r}: got a default note though a pattern was named: 「{answer}」")

    total = 2 * len(_UNNAMED) + len(_NAMED)
    return ArtPatternDefaultHonestResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ArtPatternDefaultHonestResult",
    "evaluate_art_pattern_default_honest",
]
