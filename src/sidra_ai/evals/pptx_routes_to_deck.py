"""Does a 「pptx／パワポ／PowerPoint を作って」 request route to the deck maker?

C-1250: the deck job writes a real ``.pptx`` (``decks.save_pptx``, via
python-pptx) alongside the HTML, but the creation-intent detector did not list
「pptx」「パワポ」「PowerPoint」 among its deck words. So those requests came back
``kind=unknown`` (weak) and fell to the question path's boilerplate - and
「GAMEYARD 提案の pptx を作って」 was read as a game subject and built a fishing
page. A PowerPoint request is a deck request.

The checks classify the PowerPoint spellings and a couple of controls, and
confirm each PowerPoint request routes to DECK while a game and a report still
route where they did - the fix adds deck synonyms, it does not widen DECK over
the other kinds.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PptxRoutesToDeckResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


#: (request, expected kind value). The PowerPoint spellings must be DECK; the
#: controls pin that games, reports and plain slides are unmoved.
_CASES = (
    ("pptx を作って", "deck"),
    ("パワポを作って", "deck"),
    ("PowerPoint を作って", "deck"),
    ("GAMEYARD 提案の pptx を作って", "deck"),
    ("ＰＰＴＸを作って", "deck"),  # fullwidth, NFKC-folded
    ("スライドを作って", "deck"),  # control: already worked
    ("釣りゲームを作って", "game"),  # control: not hijacked to deck
    ("レポートを作って", "document"),  # control: unmoved
)


def evaluate_pptx_routes_to_deck() -> PptxRoutesToDeckResult:
    from sidra_ai.creation.intent import detect_creation_intent

    checks = 0
    failures: list[str] = []

    for request, expected in _CASES:
        intent = detect_creation_intent(request)
        got = intent.kind.value if intent.is_creation else "not-creation"
        if got == expected:
            checks += 1
        else:
            failures.append(f"{request!r}: expected {expected}, got {got}")

    return PptxRoutesToDeckResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=len(_CASES),
        failures=tuple(failures),
    )


__all__ = ["PptxRoutesToDeckResult", "evaluate_pptx_routes_to_deck"]
