"""Can every difficulty rung of the race be finished by its weakest driver?

C-1404: with three laps on every rung, a hands-off run (no steering - the
floor of play, and the drive C-1402's measurement used: normal 51.7s and
hard 42.5s match it) finished normal and hard inside the shared sixty-second
clock but heard the buzzer on easy at two laps - the gentlest setting was
the one setting a beginner could not finish. Decision (b): the pace ladder
stays and easy runs two laps, so difficulty scales scope, not only speed.

Two things make this instrument honest where a source check is not:

* The page is driven with **no steering at all**. An expert driver finishes
  easy's three laps in ~41 seconds, so measuring skilled play would have
  called the broken configuration fine.
* Frames are ticked with **real timestamps**. The template probe feeds
  ``requestAnimationFrame`` t=0 forever, which holds the round clock at
  zero and lets a 67-second run pass a 60-second limit; here the clock is
  the judge, so it must actually run.

The C-1105 failure-beat judge keeps its loss untouched: it slows the page
through the panel's stored speed (2.4 over three default laps = 64s), not
through the easy rung.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.racing import PROBE, RACING_LAPS

#: The template probe's environment shims (handlers, rAF capture, document),
#: reused verbatim so this instrument cannot drift from the page contract.
_SHIMS = PROBE.split("SCRIPT_PLACEHOLDER")[0]

_DRIVER = """
let T = 0;
function tick(){ if (!queued) return false;
  const fn = queued; queued = null; fn(T); T += 1000/60; return true }
function key(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
/* Past the briefing gate, then hands off the wheel entirely. */
key('keydown', ' '); key('keyup', ' ');
tick(); tick();
let frames = 0;
for (let i = 0; i < 4500; i++, frames++) {
  if (raceFacts().state !== 'race') break;
  if (roundFacts().done) break;
  if (!tick()) break;
}
const end = raceFacts(); const round = roundFacts();
console.log(JSON.stringify({
  state: end.state, laps: end.laps, lapTimes: end.times.length,
  frames: frames, roundDone: round.done, roundReason: round.reason,
  ms: Math.round(round.ms),
}));
"""


@dataclass(frozen=True)
class RaceRungsResult:
    finishable: int
    rungs: int
    failures: tuple[str, ...] = ()


def evaluate_race_rungs() -> RaceRungsResult:
    if shutil.which("node") is None:
        return RaceRungsResult(0, len(RACING_LAPS), ("node is unavailable",))

    finishable = 0
    failures: list[str] = []
    for rung, laps in RACING_LAPS.items():
        page = generate_game("レースゲームを作って", difficulty=rung).html
        script = re.search(r"<script>(.*?)</script>", page, re.S)
        if script is None:
            failures.append(f"{rung}: no script")
            continue
        try:
            probe = subprocess.run(
                ["node", "-"],
                input=_SHIMS + script.group(1) + _DRIVER,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            failures.append(f"{rung}: probe unavailable ({type(exc).__name__})")
            continue
        if probe.returncode != 0:
            failures.append(f"{rung}: {probe.stderr.strip()[:60]}")
            continue
        seen = json.loads(probe.stdout)
        if seen["roundDone"] or seen["state"] != "goal":
            failures.append(
                f"{rung}: {seen['state']} at {seen['ms']}ms "
                f"(round done={seen['roundDone']}, reason={seen['roundReason']})"
            )
        elif seen["laps"] != laps or seen["lapTimes"] != laps:
            failures.append(
                f"{rung}: {seen['lapTimes']} time(s) over {seen['laps']} lap(s), "
                f"wanted {laps}"
            )
        else:
            finishable += 1
    return RaceRungsResult(finishable, len(RACING_LAPS), tuple(failures))
