"""Can an English request reach the abstract-art generator, as Japanese can?

C-1480. The ART kind carried the fewest English cues of any kind: only
"generative art" and "artwork". Japanese 「壁紙」 and 「アート」 route to ART, but
the English 「make a wallpaper」「make abstract art」「make digital art」 fell to
UNKNOWN and were declined - so an English speaker could not reach the abstract
art SIDRA does make with the natural English words for it.

The fix adds "wallpaper", "abstract art", "digital art" to ART's cues. A request
for a depiction - an illustration, a drawing, a picture - is left to decline in
both languages, because the generator makes abstract art, not a likeness (this
is deliberate, not a gap). Bare "art" stays out: it is a substring of chart,
part, smart, article, and would misroute those.

The checks read ``detect_creation_intent`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.intent import detect_creation_intent


def _kind(message: str) -> str:
    return detect_creation_intent(message).kind.value


@dataclass(frozen=True)
class EnglishArtParityResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_creation_english_art_parity() -> EnglishArtParityResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # English words for the abstract art SIDRA makes now route to ART.
    for m in ("make a wallpaper", "make abstract art", "make digital art"):
        add(_kind(m) == "art", f"{m!r}: routed to {_kind(m)}, not art")

    # Japanese art requests are unchanged, as is the existing English cue.
    add(_kind("壁紙を作って") == "art", "Japanese 壁紙 regressed")
    add(_kind("アートを作って") == "art", "Japanese アート regressed")
    add(_kind("make generative art") == "art", "English generative art regressed")

    # A depiction is still declined in both languages - ART is abstract, not a
    # likeness. These must NOT route to ART (they stay UNKNOWN).
    add(_kind("make an illustration") != "art", "illustration wrongly routed to art")
    add(_kind("make a drawing") != "art", "drawing wrongly routed to art")

    # Bare "art" substrings must not drag unrelated requests into ART.
    add(_kind("make a chart") != "art", "chart wrongly routed to art")
    add(_kind("make a smart report") == "document", "smart report misrouted")

    total = 10
    return EnglishArtParityResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["EnglishArtParityResult", "evaluate_creation_english_art_parity"]
