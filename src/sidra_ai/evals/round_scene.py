"""Which templates step their act on the round clock, read off the page.

§7 観察 5-6 at round scale: the sky steps with played time, the final act is
the brightest, and the sixty seconds still end the go. ``creation_round_scene``
measures that, and for a long time it measured fishing, catch and puzzle while
saying nothing at all about the other seven.

The shooter had carried the same contract since C-1315 - its page says so
above ``ACT`` ("the 60-second round in three acts ... the final third is the
brightest sky of the fight") and ``setPal``'s third act holds the same +0.22
the other three hold. The only thing that kept it out of the judge's table is
how it is spelled: fishing, catch and puzzle write the act inline as
``ROUND_MS/(ROUND_LIMIT_MS/3)``, and the shooter factored the identical thirds
into ``actOf()``. Nothing failed when it drifted out of view, because a judge
that names three templates and stays quiet about the rest cannot fail that way
(C-1795 - the caller-side form of C-1755, which the C-1791 guard does not
reach because that one watches ``*_one`` workers, not hard-coded tables).

This lives in a module rather than inline in the judge so the judge and its
tests read the same code. The first draft of those tests carried their own
copy of this function; sabotaging the judge's copy changed nothing, and the
tests went on passing while measuring a reader nobody used (C-1793's single
source, learned again).
"""

from __future__ import annotations

import re

#: A call to ``setScene``, not its definition, with the argument that follows.
#: Bounded rather than paren-balanced on purpose: the argument only has to be
#: recognised, not evaluated, and an unbounded read walks off into the rest of
#: the page (the first draft of this did exactly that and called the shooter
#: clock-free and the duel clock-bound - both wrong).
#:
#: Honest about its own coverage: the ``(?<!function )`` is belt-and-braces.
#: Removing it changes the verdict on **none of the ten pages** (measured
#: 2026-09-14), because what it lets through - ``i){SCENE=i|0}`` and the
#: seventy characters after it - contains no clock either way. So no test
#: here is holding it up, and a destruction that deletes it passes. It stays
#: because the definition is not a call and reading it as one is wrong even
#: when it is harmless; it is recorded as unguarded rather than counted.
CALL = re.compile(r"(?<!function )setScene\(([^)\n]{0,70})")

#: ``ROUND_MS`` is the inline spelling. ``t >=`` is the fixed-step play counter
#: the shooter counts its thirds in - C-1607/C-1608's gate advances that
#: counter on real time rather than on the display's refresh rate, so the two
#: spellings mean the same clock (§26).
CLOCK = re.compile(r"ROUND_MS|\bt\s*>=")


def clock_bound(script: str) -> bool:
    """Does this page's act step on the round clock?

    One level of helper is resolved, and that single level is the whole
    point: ``setScene(actOf())`` and the inline ``setScene(Math.min(2,
    ROUND_MS/(ROUND_LIMIT_MS/3)))`` have to read the same here, or this
    re-creates the bug it exists to catch.
    """

    seen: list[str] = []
    for arg in CALL.findall(script):
        arg = arg.strip()
        if arg in ("i", ""):
            continue
        helper = re.match(r"^([A-Za-z_]\w*)\($", arg)
        if helper:
            body = re.search(
                r"function\s+%s\([^)]*\)\{return ([^}]*)\}" % helper.group(1), script
            )
            seen.append(body.group(1) if body else arg)
        else:
            seen.append(arg)
    return bool(CLOCK.search(" ".join(seen)))


#: The six templates whose act steps on something other than the clock, and
#: what it steps on. Their brightness is spent over a course or a state, which
#: is ``creation_scene_palette``'s contract, not this one. Named rather than
#: left implicit: a template absent from both lists is how the shooter hid.
ELSEWHERE: dict[str, str] = {
    "duel": "hp",
    "kaiju": "boss phase",
    "platformer": "走者の x",
    "marble": "玉の z",
    "racing": "周回",
    "adventure": "room",
}
