"""Does the on-screen pad draw only the buttons the game actually uses?

C-1244: the touch pad (``touchpad.py``) synthesises keyboard events so a phone
can play the games, and it drew the full set - ◀ ▶ ▲ ▼ plus A and R - on every
template regardless of what that template reads. The default fishing game uses
one control (SPACE, 「合わせる」), so four directional buttons sat over a
352×158px play field on an iPhone 12 doing nothing: a phone player taps ◀ and
nothing happens, and the dead button hides the fish and the timing band. Only
``adventure`` and ``puzzle`` (which read every direction) were unaffected.

The fix draws a pad button only when the template's own handlers read its key.
``touchpad.keys_read`` already names those keys, so the generation injects a
``PAD_ACTIVE`` set and ``padButtons`` filters by it.

Layout cannot be computed offline, so the checks pin the contract on the
generated HTML: the pad filters its buttons by ``PAD_ACTIVE`` at all, and for
every supported genre the set that will be drawn equals the set of pad keys the
template reads - no dead button drawn, and no live button removed. The
iPhone-emulation proof (the D-pad gone from fishing, A/R remaining) runs at fix
time and is recorded in the loop log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PadOnlyUsedButtonsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


#: The exact filter ``padButtons`` must apply. Pinned rather than matched
#: loosely so an inverted filter (``!PAD_ACTIVE.has``) - which keeps the dead
#: buttons and drops the live ones - is caught, not read as "filtered".
_FILTER = ".filter(b=>PAD_ACTIVE.has(b.id))"


def _parse_pad_active(script: str) -> set[str] | None:
    """The set the pad will draw, or ``None`` if it declares none.

    ``None`` means the pre-fix behaviour: ``padButtons`` returns the full set,
    so every pad key is drawn.
    """

    m = re.search(r"PAD_ACTIVE\s*=\s*new Set\(\s*\[([^\]]*)\]\s*\)", script)
    if m is None:
        return None
    return {token for token in re.findall(r"""["']((?:\\.|[^"'\\])*)["']""", m.group(1))}


def _drawn_set(script: str, pad_keys: tuple[str, ...]) -> set[str]:
    """The buttons this page will actually render.

    ``PAD_ACTIVE`` only narrows the pad if ``padButtons`` filters by it, so a
    declaration that nothing reads is the full set on screen - the same as no
    declaration at all.
    """

    active = _parse_pad_active(script)
    if active is None or _FILTER not in script:
        return set(pad_keys)
    return active


def evaluate_pad_only_used_buttons() -> PadOnlyUsedButtonsResult:
    from sidra_ai.creation.games import TEMPLATES, _script_of, generate_game
    from sidra_ai.creation.touchpad import PAD_KEYS, keys_read

    pad = set(PAD_KEYS)
    checks = 0
    total = 0
    failures: list[str] = []

    # 1: the pad actually filters its drawn buttons by PAD_ACTIVE. Without this
    # a correct PAD_ACTIVE would be inert - padButtons would still draw them all.
    total += 1
    sample = _script_of(generate_game("釣りゲームを作って").html)
    if _FILTER in sample and "PAD_ACTIVE=new Set(" in sample:
        checks += 1
    else:
        failures.append("padButtons does not filter (positively) by PAD_ACTIVE")

    # 2..: for each supported genre, the buttons that will be drawn equal the
    # pad keys the running page reads. Computed on the finished script, not the
    # bare template: restart's `r` and some templates' space come from wrapper
    # preambles, so a per-template check would call a live R button dead.
    for genre in sorted(TEMPLATES):
        total += 1
        script = _script_of(generate_game(f"{genre} を作って").html)
        expected = keys_read(script) & pad
        drawn = _drawn_set(script, PAD_KEYS)
        dead = drawn - expected
        missing = expected - drawn
        if not dead and not missing:
            checks += 1
        else:
            parts = []
            if dead:
                parts.append("dead=" + ",".join(sorted(dead)))
            if missing:
                parts.append("missing=" + ",".join(sorted(missing)))
            failures.append(f"{genre}: " + "; ".join(parts))

    return PadOnlyUsedButtonsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["PadOnlyUsedButtonsResult", "evaluate_pad_only_used_buttons"]
