"""Are the two colours the colour-blindness judge separates the two the page paints?

``creation_cvd_info_pair`` (C-1330, §20) takes a theme's ``accent`` and
``alert``, pushes both through the Machado severity-1.0 matrices, and requires
their Lab ΔE to clear a floor - four themes times three kinds of colour vision,
twelve cells. The arithmetic is right and this judge does not touch it.

What it never did was look at a page. Its input is ``theme.tokens``; it calls
no generator and runs no probe. Its label says 「主役と敵が別の色」 - hero and
foe are different colours - and nobody checked that those two tokens are the
two a player has to tell apart. That is C-1640's ledger problem: read the
running page, not the table the page was built from.

Measured over 900 frames of real drawing per template: **eight of the ten
paint both tokens.** Two do not, and for reasons that are design rather than
oversight - so they are named here with the reason rather than counted as
failures:

* ``marble`` paints neither. Every surface goes through ``shade(hex, k)`` so
  that depth reads as brightness, and a shaded variant is never the raw token.
* ``platformer`` paints ``accent`` and no ``alert``. Its danger is the gap
  between ledges - an absence, not an object - and ``ALERT_JUICE`` appears
  only when the lantern lights.

**What this does and does not establish.** It answers 「are both colours on
this page at all」, not 「is the foe the alert one」. Found by destruction:
recolouring every one of shooter's three ``MAGENTA_TOKEN`` draw calls to the
hero's cyan did not move the number, because the shared HUD, result strip and
juice preambles paint ``alert`` too. So this backs up half of
``creation_cvd_info_pair``'s premise - the colours it separates are colours
the player actually sees - and leaves the other half, which element wears
which, unmeasured. Saying it verified 「主役と敵が別の色」 would be the
overstatement this judge exists to remove.

**Both directions.** A judge that only asked 「is the pair painted」 would be
satisfied by writing a reason for all ten; one that only checked the reasons
would be satisfied by a product that painted nothing. A template in
``CVD_PAIR_UNDRAWN`` must actually be missing what its reason says is missing.

The window matters and is part of the contract. Written first at three frames,
the census reported that racing painted no ``alert`` - racing's obstacles are
``MAGENTA_TOKEN`` squares that spawn on an interval and simply had not
appeared yet. **A short sample looks exactly like a missing feature.**
"""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.probekeys import KEY_EVENT_JS
from sidra_ai.creation.themes import DEFAULT_THEME

#: Frames of drawing recorded per template, after two hundred frames of play.
#: Three was not enough: see the module docstring.
FRAMES = 900

#: Templates that do not paint the pair, and why. Neither is unguarded - both
#: carry the distinction in a channel the token pair does not describe.
CVD_PAIR_UNDRAWN: dict[str, str] = {
    "marble": "奥行きを明るさで描くので、あらゆる面が `shade(hex,k)` を通り、生のトークンは一度も塗られない",
    "platformer": "危険が「物」ではなく足場の切れ目で、`ALERT_JUICE` は灯籠が点いたときだけ出る",
}

_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)

_PROBE = KEY_EVENT_JS + """
const seen = {};
let _fill = '', _stroke = '';
const _rec = {
  fillRect: () => { if (_fill) seen[_fill.toLowerCase()] = 1 },
  strokeRect: () => { if (_stroke) seen[_stroke.toLowerCase()] = 1 },
  fill: () => { if (_fill) seen[_fill.toLowerCase()] = 1 },
  stroke: () => { if (_stroke) seen[_stroke.toLowerCase()] = 1 },
  fillText: () => { if (_fill) seen[_fill.toLowerCase()] = 1 },
};
const ctx = new Proxy(_rec, {
  get: (o, k) => (k in o ? o[k] : (k === 'canvas'
    ? { width: 720, height: 320 } : (typeof k === 'string' ? () => {} : undefined))),
  set: (o, k, v) => { if (k === 'fillStyle') _fill = String(v);
                      if (k === 'strokeStyle') _stroke = String(v); return true } });
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => ctx }) };
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function _probeFrame(){ if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }
function _probePress(k){ const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e)) }
_probePress(' ');
/* Play a while first: a title screen paints the gate, not the game. */
for (let i = 0; i < 200; i++) _probeFrame();
for (const k of Object.keys(seen)) delete seen[k];
for (let i = 0; i < FRAMES_TOKEN; i++) _probeFrame();
console.log(JSON.stringify({ painted: Object.keys(seen) }));
"""


@dataclass(frozen=True)
class CvdDrawnResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    accounted: int = 0
    painting: tuple[str, ...] = ()


def _run(job: tuple[str, str]) -> tuple[str, list[str] | None]:
    template, script = job
    try:
        run = subprocess.run(
            ["node", "-"],
            input=_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
                "FRAMES_TOKEN", str(FRAMES)
            ),
            capture_output=True,
            text=True,
            timeout=240,
        )
        if run.returncode != 0:
            return template, None
        return template, list(json.loads(run.stdout.strip().splitlines()[-1])["painted"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return template, None


def evaluate_cvd_pair_is_drawn() -> CvdDrawnResult:
    checks = 0
    failures: list[str] = []
    painting: list[str] = []

    accent = DEFAULT_THEME.tokens["accent"].lower()
    alert = DEFAULT_THEME.tokens["alert"].lower()

    jobs = []
    for template in sorted(TEMPLATES):
        page = generate_game("ゲームを作って", template=template).html
        script = _SCRIPT.search(page)
        if script is None:
            failures.append(f"{template}: 頁に script が無い")
            continue
        jobs.append((template, script.group(1)))

    # Ten subprocesses waiting on a child hold no GIL (C-1857).
    with ThreadPoolExecutor(max_workers=4) as pool:
        done = dict(pool.map(_run, jobs))

    for template in sorted(TEMPLATES):
        painted = done.get(template)
        if painted is None:
            failures.append(f"{template}: 運転器が動かせない")
            continue
        has_accent, has_alert = accent in painted, alert in painted
        why = CVD_PAIR_UNDRAWN.get(template)
        if why is None:
            # The judge's premise: both colours it separates are on screen.
            if has_accent and has_alert:
                checks += 1
                painting.append(template)
            else:
                missing = [
                    name
                    for name, ok in (("accent", has_accent), ("alert", has_alert))
                    if not ok
                ]
                failures.append(
                    f"{template}: {'/'.join(missing)} を塗らないのに理由が書かれていない"
                )
            continue
        # The other direction: a reason has to describe something real - a
        # template listed as not painting the pair must really not paint it,
        # or the list is a way of excusing everything.
        if has_accent and has_alert:
            failures.append(f"{template}: 理由が書いてあるのに 2 色とも塗っている")
        else:
            checks += 1
        if len(why.strip()) > 20:
            checks += 1
        else:
            failures.append(f"{template}: 理由が書かれていない")

    accounted = len(painting) + len(
        [k for k in CVD_PAIR_UNDRAWN if k in TEMPLATES]
    )
    if accounted == len(TEMPLATES):
        checks += 1
    else:
        failures.append(f"{accounted}/{len(TEMPLATES)} の型しか説明が付いていない")

    stray = sorted(set(CVD_PAIR_UNDRAWN) - set(TEMPLATES))
    for key in stray:
        failures.append(f"{key}: 表に在るが型ではない")

    return CvdDrawnResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
        accounted=accounted,
        painting=tuple(painting),
    )


__all__ = ["CVD_PAIR_UNDRAWN", "FRAMES", "CvdDrawnResult", "evaluate_cvd_pair_is_drawn"]
