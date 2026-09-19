"""Does the adapt panel announce a step only when a step was actually taken?

C-1775. After three losses the game steps once toward the easy end of the
author's ladder and says so, next to the panel: 「今の調整: 1 段やさしく」.
The panel decided what to say with ``adaptEasing()`` - streak >= 3, not manual,
more than one rung - but the function that actually eases, ``adaptSpeed()``,
bails at the floor (``if(at<=0)return v``): at the easiest rung there is no
lower step to move to, so it returns the value unchanged. On an easy-difficulty
game the two disagreed - ``adaptEasing()`` true, no ease applied - and the page
claimed 「1 段やさしく」 to a losing player when nothing had changed, the exact
false help aimed at the very player the feature exists for.

``adaptEasing()`` is now floor-aware: it finds the base speed's rung the same
way ``adaptSpeed`` does and answers true only when a lower rung exists. The
checks run the real preamble in node for a floor game, a mid-ladder game, and a
below-threshold streak, and read both the panel text and what ``adaptSpeed``
actually returned.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.adapt import preamble_for
from sidra_ai.creation.canvaswords import CANVAS_WORDS, words_js

_STEPS = (1.0, 2.0, 3.0)  # author's ladder, easy first
#: Taken from the page's own table rather than typed again here (C-1965):
#: the panel says what ``CANVAS_WORDS`` says, so a reworded line moves both
#: at once instead of leaving this eval measuring a sentence nobody writes.
_EASE = CANVAS_WORDS["now_eased_open"][0].split(": ")[-1].split("（")[0]
_STANDARD = CANVAS_WORDS["now_standard"][0]

_HARNESS = """
let captured=null;
const handlers={};
globalThis.localStorage={_s:{},getItem(k){return k in this._s?this._s[k]:null},
  setItem(k,v){this._s[k]=String(v)},removeItem(k){delete this._s[k]}};
globalThis.document={readyState:'loading',addEventListener:(t,fn)=>{handlers[t]=fn},
  createElement:()=>({textContent:'',style:{}}),
  querySelector:()=>({appendChild:(x)=>{captured=x}}),
  body:{appendChild:(x)=>{captured=x}}};
WORDS
PREAMBLE
localStorage.setItem(ADAPT_KEY, String(STREAK));
const speedOut = adaptSpeed(ADAPT_BASE);
const easing = adaptEasing();
adaptPanel();
console.log(JSON.stringify({easing:easing, speedOut:speedOut, base:ADAPT_BASE,
  eased:(speedOut!==ADAPT_BASE), panel:(captured?captured.textContent:null)}));
"""


def _probe(base: float, streak: int) -> dict:
    # The page gives every preamble the word table at the top; a probe that
    # runs one preamble alone has to give it the same thing, or it measures
    # a page that could not exist (C-1965).
    src = (
        _HARNESS.replace("WORDS", words_js())
        .replace("PREAMBLE", preamble_for("t", _STEPS, base))
        .replace("STREAK", str(int(streak)))
    )
    run = subprocess.run(
        ["node", "-"], input=src, capture_output=True, text=True, timeout=120
    )
    if run.returncode != 0:
        raise ValueError(run.stderr.strip()[:200])
    return json.loads(run.stdout.strip().splitlines()[-1])


@dataclass(frozen=True)
class AdaptPanelResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_adapt_panel_easing_matches_actual_ease() -> AdaptPanelResult:
    total = 6
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return AdaptPanelResult(False, 0, total, ("node is unavailable",))

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    floor = _probe(min(_STEPS), 3)   # already the easiest rung, on a losing streak
    mid = _probe(_STEPS[1], 3)       # a rung above the floor, same streak
    below = _probe(_STEPS[1], 2)     # a rung above the floor, below the threshold

    # --- the fix: no step is announced at the floor -----------------------
    add(_EASE not in (floor.get("panel") or ""),
        f"A: the panel claims a step at the easiest rung: {floor.get('panel')!r}")
    # --- ground truth: adaptSpeed really did nothing at the floor ---------
    #     (a dropped floor guard returns undefined - JSON omits it - which is
    #     not "unchanged" and must read as a failure, not crash the eval.)
    add(floor.get("speedOut") == floor.get("base"),
        f"B: adaptSpeed changed the speed at the floor: {floor.get('speedOut')} vs {floor.get('base')}")
    # --- the honest label at the floor -----------------------------------
    add(floor.get("panel") == _STANDARD,
        f"E: the floor panel is not the standard label: {floor.get('panel')!r}")

    # --- real help is still announced above the floor --------------------
    add(_EASE in (mid.get("panel") or ""),
        f"C: a genuinely eased load no longer announces the step: {mid.get('panel')!r}")
    # --- ground truth: adaptSpeed really eased above the floor ------------
    add(bool(mid.get("eased")) and mid.get("speedOut") is not None
        and mid.get("speedOut") < mid.get("base"),
        f"D: adaptSpeed did not ease above the floor: {mid.get('speedOut')} vs {mid.get('base')}")

    # --- restraint: nothing announced below the streak threshold ----------
    add(_EASE not in (below.get("panel") or ""),
        f"F: the panel claims a step below the loss threshold: {below.get('panel')!r}")

    return AdaptPanelResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["AdaptPanelResult", "evaluate_adapt_panel_easing_matches_actual_ease"]
