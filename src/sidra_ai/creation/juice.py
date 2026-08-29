"""Screen shake, hitstop and particles - the half of game feel after sound.

The knowledge base (``docs/research/game-design-notes.md`` §1) puts the
order plainly: sound first, then shake and hitstop, then particles. C-1017
did the sound. This is the rest, and it is built the same way - one preamble
shared by every template, so a new template gets feel from the day it is
written rather than the day someone remembers to add it.

Three effects, each with a reason for the shape it has:

* ``shake(weight)`` kicks the **canvas element** and decays fast. Vlambeer's
  rule is that the kick is proportional to the weight of the event; a
  constant rattle reads as a bug. Moving the element rather than every draw
  call means no template has to cooperate with the camera.
* ``hitstop(frames)`` freezes the loop for a few frames by re-scheduling the
  animation callback without running it. The frame that was already drawn
  stays on screen, which is what a hit landing is supposed to feel like -
  and, unlike a flag templates have to check, it cannot be half-applied.
* ``burst(x, y, n, colour)`` spawns particles drawn after the game each
  frame. Templates only say where and how many.

**Reduced motion**: ``shake`` and ``burst`` become no-ops - that is the
setting's whole point, and §1 is explicit that these are the decorative
half. ``hitstop`` stays: it moves nothing, it withholds motion, and a person
who asked for less movement is not asking for hits to feel weightless. The
game is fully playable with all three off; ``probe_source`` runs the code
both ways so this is measured rather than asserted.
"""

from __future__ import annotations

#: Names the preamble introduces. Held to by a test, as with the animation
#: preamble: a template that happened to define ``shake`` would break only in
#: the generated page.
PREAMBLE_NAMES: tuple[str, ...] = (
    "shake",
    "hitstop",
    "burst",
    "shakeAmount",
    "particleCount",
)

JUICE_PREAMBLE = """
/* --- juice: shake, hitstop, particles (knowledge base §1) ------------- */
const JCV=document.getElementById('stage');
let SHAKE=0,HITSTOP=0,PARTS=[];
/* Weight in "how big was this": 1 a footstep, 6 a hit, 12 a death. The kick
   is that many pixels and is gone in a few frames. */
function shake(weight){if(REDUCED)return;SHAKE=Math.max(SHAKE,weight)}
function hitstop(frames){HITSTOP=Math.max(HITSTOP,frames)}
function burst(x,y,n,colour){if(REDUCED)return;
  for(let i=0;i<n;i++){const a=Math.random()*Math.PI*2,s=0.6+Math.random()*1.8;
    PARTS.push({x:x,y:y,vx:Math.cos(a)*s,vy:Math.sin(a)*s-0.6,
      life:1,c:colour||'CYAN_TOKEN'})}}
function shakeAmount(){return SHAKE}
function particleCount(){return PARTS.length}
function stepShake(){if(!JCV)return;
  if(SHAKE>0.05){SHAKE*=0.78;
    const dx=(Math.random()*2-1)*SHAKE,dy=(Math.random()*2-1)*SHAKE;
    JCV.style.transform='translate('+dx.toFixed(2)+'px,'+dy.toFixed(2)+'px)'}
  else if(SHAKE!==0){SHAKE=0;JCV.style.transform=''}}
function stepParticles(){if(!PARTS.length||!JCV)return;
  const c=JCV.getContext('2d');c.save();
  PARTS=PARTS.filter(p=>{p.x+=p.vx;p.y+=p.vy;p.vy+=0.12;p.life-=0.045;
    if(p.life<=0)return false;
    c.globalAlpha=Math.max(0,p.life);c.fillStyle=p.c;
    c.fillRect(p.x-1.5,p.y-1.5,3,3);return true});
  c.restore()}
/* The loop wrapper does three jobs in one place: hold the frame during a
   hitstop, draw the particles over whatever the game drew, and move the
   canvas. Wrapped before the pad wraps it, so the pad stays on top. */
const JUICE_RAF=requestAnimationFrame;
requestAnimationFrame=function(fn){
  return JUICE_RAF(function tick(t){
    /* Re-scheduled rather than skipped: dropping the callback would end the
       template's loop instead of pausing it. */
    if(HITSTOP>0){HITSTOP--;JUICE_RAF(tick);return}
    fn(t);stepParticles();stepShake()})};
"""

#: Runs the three effects with the viewer's setting pinned, and prints what
#: they did. The metric executes this in node, so "reduced motion turns the
#: decoration off" is observed rather than grepped.
PROBE = """
globalThis.matchMedia = (q) => ({ matches: REDUCED_INPUT });
globalThis.document = { getElementById: () => null };
globalThis.requestAnimationFrame = (fn) => 0;
ANIMATION_PLACEHOLDER
JUICE_PLACEHOLDER
shake(8);
burst(10, 10, 12, '#fff');
hitstop(4);
console.log(JSON.stringify({
  reduced: REDUCED,
  shake: shakeAmount(),
  particles: particleCount(),
  hitstop: HITSTOP,
}));
"""


def probe_source(*, reduced: bool) -> str:
    """The harness with the viewer's setting pinned, ready for ``node -``."""

    from sidra_ai.creation.animation import PREAMBLE as ANIMATION_PREAMBLE

    return (
        PROBE.replace("REDUCED_INPUT", "true" if reduced else "false")
        .replace("ANIMATION_PLACEHOLDER", ANIMATION_PREAMBLE)
        .replace("JUICE_PLACEHOLDER", JUICE_PREAMBLE)
    )


__all__ = ["JUICE_PREAMBLE", "PREAMBLE_NAMES", "PROBE", "probe_source"]
