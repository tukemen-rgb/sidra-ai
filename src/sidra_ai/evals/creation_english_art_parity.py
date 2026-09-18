"""Can an English request reach the abstract-art generator, as Japanese can?

C-1480. The ART kind carried the fewest English cues of any kind: only
"generative art" and "artwork". Japanese 「壁紙」 and 「アート」 route to ART, but
the English 「make a wallpaper」「make abstract art」「make digital art」 fell to
UNKNOWN and were declined - so an English speaker could not reach the abstract
art SIDRA does make with the natural English words for it.

The fix adds "wallpaper", "abstract art", "digital art" to ART's cues. Bare
"art" stays out: it is a substring of chart, part, smart, article, and would
misroute those.

**C-1948 corrected the other half of this file.** It used to say a depiction
- an illustration, a drawing, a picture - "is left to decline in both
languages, because the generator makes abstract art, not a likeness", and it
checked that on the English side only. That stopped being true at C-1804,
which added 「絵」 and 「イラスト」 to the Japanese cues: measured 2026-09-18,
「絵を作って」 and 「イラストを作って」 both route to ART. So this file spent
two items asserting a principle its own product had abandoned, and the
checks could not see it because none of them looked at the Japanese side of
that principle.

What the product actually does with a depiction request, measured through
the real router: it makes the abstract art and **says so** - 「依頼にあった
題材は描いていません。アートは抽象の模様（フロー / 軌道）です」 and, in
English, "The subject in the request is not drawn. The art is an abstract
pattern". 「make artwork of an owl」 has always done that. The decline was
never the product's answer to a named subject; it was only what the ordinary
English words happened to get. The two checks below are now parity checks -
English and Japanese must read the same request the same way - which is what
this file is named for.

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

    # A depiction word reads the same in both languages (C-1948). Written as
    # a comparison rather than as "== art" on purpose: if one side is ever
    # decided to decline these, the other has to be decided with it, and this
    # check is what makes that impossible to do by halves.
    add(
        _kind("make an illustration") == _kind("イラストを作って"),
        "「make an illustration」 and 「イラストを作って」 are read differently",
    )
    add(
        _kind("make a drawing") == _kind("絵を作って"),
        "「make a drawing」 and 「絵を作って」 are read differently",
    )

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
