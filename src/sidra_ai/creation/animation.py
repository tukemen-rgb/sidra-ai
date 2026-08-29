"""Motion for a generated page, and the switch that turns it off.

Two things make animation in a generated artifact worth its own module.

The first is that ``prefers-reduced-motion`` is a requirement, not a polish
item: GAMEYARD's design rules ask for it, and a person who set that switch
did so because motion makes them ill. So the preamble below decides once,
at load, and every decorative movement reads that decision rather than
implementing its own opinion.

The second is what "off" has to mean. Reduced motion stops the *decorative*
motion - an idle sprite cycling, a float bobbing, a transition easing in -
and leaves the game running. A page that froze its own game loop under
reduced motion would technically respect the setting and would also be
broken, which is why ``FRAME`` collapses to a constant while the loop that
calls it keeps being called.

The helpers are plain functions on purpose: they are exercised by *running*
them in node, so the number that says "this page animates" is a behavioural
measurement rather than a grep for the word ``transition``.
"""

from __future__ import annotations

#: Injected at the top of every template's script. Defines three names the
#: templates use and nothing else, so a template that ignores animation is
#: unaffected by its presence.
#:
#: * ``REDUCED``  - the viewer's setting, read once.
#: * ``ease(t)``  - easeOutCubic on 0..1, or the identity when reduced, so a
#:                  movement that would glide instead snaps.
#: * ``FRAME(n, fps, now)`` - which frame of an ``n``-frame decorative cycle
#:                  to draw. Pinned to 0 when reduced.
PREAMBLE = """
const REDUCED = (typeof matchMedia === 'function')
  && matchMedia('(prefers-reduced-motion: reduce)').matches;
function ease(t){t=Math.min(1,Math.max(0,t));
  return REDUCED ? t : 1-Math.pow(1-t,3)}
function FRAME(n, fps, now){
  if (REDUCED) { return 0 }
  return Math.floor(now * fps / 1000) % n}
""".strip()

#: Names the preamble is allowed to introduce. Kept as data so a test can
#: assert the preamble adds exactly these and no more: a template that
#: happened to use a name the preamble also defined would break in a way
#: that only shows up in the generated page.
PREAMBLE_NAMES: tuple[str, ...] = ("REDUCED", "ease", "FRAME")

#: A short harness that runs the preamble's helpers and prints what they do.
#: Executed by the metric, so "the page animates and stops when asked" is
#: checked by observing behaviour rather than by matching source text.
PROBE = """
globalThis.matchMedia = (q) => ({ matches: REDUCED_INPUT });
PREAMBLE_PLACEHOLDER
const frames = [FRAME(4, 12, 0), FRAME(4, 12, 100), FRAME(4, 12, 200), FRAME(4, 12, 300)];
console.log(JSON.stringify({
  reduced: REDUCED,
  easeStart: ease(0),
  easeEnd: ease(1),
  easeMid: ease(0.5),
  frames: frames,
  distinctFrames: new Set(frames).size,
}));
"""


def probe_source(*, reduced: bool) -> str:
    """The harness with the viewer's setting pinned, ready for ``node -``."""

    return PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "PREAMBLE_PLACEHOLDER", PREAMBLE
    )


#: Drives a generated page's own loop in node with the browser stubbed out,
#: and reports how many frames it managed. The property this exists for -
#: "reduced motion slows the decoration, never the game" - used to be checked
#: by forbidding the string ``if(REDUCED)return`` anywhere on the page. That
#: proxy stopped meaning what it said the moment a *decorative* effect
#: legitimately opted out of reduced motion (C-1020's shake and particles do
#: exactly that, correctly). Counting frames asks the real question instead,
#: and catches a loop gated on ``REDUCED`` that no string check would.
LOOP_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = () => {};
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null, scheduled = 0;
globalThis.requestAnimationFrame = (fn) => { scheduled++; queued = fn; return scheduled };
SCRIPT_PLACEHOLDER
/* The page has scheduled its first frame by now. Run the queue by hand: a
   loop that keeps asking for another frame keeps handing one back. */
let ran = 0;
for (let i = 0; i < FRAMES_INPUT && queued; i++) {
  const fn = queued; queued = null; fn(i * 16); ran++;
}
console.log(JSON.stringify({ reduced: REDUCED, scheduled: scheduled, ran: ran }));
"""


def loop_probe(script: str, *, reduced: bool, frames: int = 40) -> str:
    """The page's script wrapped so its loop can be counted in node."""

    return (
        LOOP_PROBE.replace("REDUCED_INPUT", "true" if reduced else "false")
        .replace("FRAMES_INPUT", str(frames))
        .replace("SCRIPT_PLACEHOLDER", script)
    )


def with_animation(script: str) -> str:
    """Put the preamble in front of a template's script."""

    return f"{PREAMBLE}\n{script}"


__all__ = [
    "LOOP_PROBE",
    "PREAMBLE",
    "PREAMBLE_NAMES",
    "loop_probe",
    "probe_source",
    "with_animation",
]
