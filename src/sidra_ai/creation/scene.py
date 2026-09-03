"""Per-scene environment palettes for the generated game pages.

Where :mod:`sidra_ai.creation.themes` answers "what colour is this *work*",
this module answers "what colour is this *place*". The two are deliberately
orthogonal: a theme is picked once per artifact from the request, a scene
palette changes as the player moves through the artifact, and the second is
implemented as a *transform of* the first so that naming a theme still wins.
A scene that hard-coded a green never noticed the theme; a scene that shifts
the theme's own hue keeps four themes readable and still separates rooms.

The rules are from the owner's viewing notes
(``docs/research/game-design-notes.md`` §7 観察 5-6), which machine-extracted
the dominant four colours of thirty scenes:

* one dark neutral base with a **single accent hue per location** - scenes
  are told apart by hue, not by redrawing the furniture;
* the **brightest frame of the whole episode is reserved for the climax**
  (``#c9a2c8`` at the kaiju confrontation, near-black everywhere else), so
  brightness is a dramatic budget rather than a per-scene decision.

Two constraints hold this to the accessibility rules in §4:

* the floor and the wall are transformed *by the same function*, so their
  value ordering - the thing that makes a wall read as a wall - survives
  every scene, and the terrain is still carried by shape and edge highlight;
* the step is taken in **relative luminance**, not in HSL lightness:
  ``L + k*(1-L)`` to brighten and ``L*(1+k)`` to darken, then the lightness
  that hits that luminance is solved for. Hue carries most of the brightness
  in sRGB - a green at ``l=0.9`` outshines a magenta at ``l=0.9`` - so a
  lightness offset let a forest outshine the climax on the light theme
  before this was measured. Aiming at luminance keeps "brightest scene last"
  true for every theme and every hue, and neither end clips.

A palette entry is ``[hue shift in degrees, saturation multiplier,
lightness k]``. The numbers are read back off the running page by the
templates' probes rather than trusted from here.
"""

from __future__ import annotations

#: Adventure, one entry per room: forest, cave, altar.
#:
#: The walk is green -> blue-violet -> the brightest thing in the game. The
#: cave is the darkest of the three on purpose: the valley is what makes the
#: altar land (the scene-scale version of the loud/quiet wave in §7 観察 6).
ADVENTURE_PALETTE: tuple[tuple[float, float, float], ...] = (
    (-83.0, 1.15, 0.03),
    (47.0, 1.25, -0.18),
    (80.0, 1.05, 0.20),
)

#: Kaiju, one entry per phase: legs (advance), head open (stagger), down.
#:
#: Dust while it is walking, a colder flash when it reels, and the single
#: brightest frame of the fight when the body is finally shown.
KAIJU_PALETTE: tuple[tuple[float, float, float], ...] = (
    (18.0, 0.75, 0.02),
    (47.0, 1.10, 0.09),
    (80.0, 1.05, 0.22),
)

#: Racing, one entry per lap: opening lap, middle lap, final lap.
#:
#: The hue steps warm -> cool -> the brightest frame of the run, so a glance
#: at the air says which lap this is before the HUD is read - and the final
#: lap gets the brightness budget, the lap-scale version of reserving the
#: peak for the climax (§7 観察 6).
RACING_PALETTE: tuple[tuple[float, float, float], ...] = (
    (-28.0, 0.90, 0.03),
    (36.0, 1.10, 0.10),
    (80.0, 1.05, 0.22),
)

#: Platformer, one entry per stretch of the course: opening, midway, the
#: run-up to the goal.
#:
#: A cool opening, a warmer middle, and the goal stretch keeps the largest
#: share of the brightness budget - the flag is the climax, so it is the
#: brightest thing the course ever shows (§7 観察 6).
PLATFORMER_PALETTE: tuple[tuple[float, float, float], ...] = (
    (-58.0, 1.12, 0.02),
    (36.0, 1.20, 0.09),
    (78.0, 1.05, 0.21),
)

#: Shooter, one entry per act of the 60-second round: patrol, raid, the
#: final stretch.
#:
#: The HUD has always counted 第 N 波; this is the sky agreeing with it. A
#: cold opening, a warmer middle as the formations thicken, and the last
#: third of the round holds the brightness budget - the wave you are on
#: when the clock runs out is the climax, so it is the brightest sky of
#: the fight (§7 観察 5-6).
SHOOTER_PALETTE: tuple[tuple[float, float, float], ...] = (
    (-52.0, 0.85, 0.02),
    (24.0, 1.15, 0.08),
    (80.0, 1.05, 0.22),
)

#: Marble, one entry per stretch of the corridor: the roll-out, the deep
#: middle, the run-in.
#:
#: The course is one straight line, so distance is the scene: a cool
#: opening sky, a warmer middle, and the final stretch holds the
#: brightness budget - the last gates are rolled at under the brightest
#: sky of the run (§7 観察 5-6).
MARBLE_PALETTE: tuple[tuple[float, float, float], ...] = (
    (-46.0, 0.9, 0.03),
    (28.0, 1.12, 0.10),
    (80.0, 1.05, 0.22),
)

#: Fishing, one entry per third of the sixty-second round: first light,
#: full day, the golden last stretch.
#:
#: The other courses spend the brightness budget over distance; a timing
#: game has no distance, so the round clock is the journey and the last
#: twenty seconds get the peak - the cast you land as time runs out is
#: the climax of the session (§7 観察 5-6 over §8's sixty seconds).
FISHING_PALETTE: tuple[tuple[float, float, float], ...] = (
    (-40.0, 0.85, 0.02),
    (30.0, 1.10, 0.10),
    (80.0, 1.05, 0.22),
)

#: Installed before every template. Defines the transform and leaves the
#: palette itself to the template, which calls ``setPal`` once at boot.
SCENE_PREAMBLE = """
/* Per-scene environment palette (game-design-notes.md §7 観察 5-6).
   A scene shifts the THEME's colour rather than replacing it, so all four
   themes keep their identity and still show a difference between scenes.
   Floor and wall go through the same transform, so the value gap that makes
   a wall read as a wall survives - the palette carries mood only. */
let SPAL=[[0,1,0]],SCENE=0;
/* The floor is the anchor every other colour in the frame moves with. */
const SCENE_FLOOR='SURFACE_TOKEN';
function setPal(p){SPAL=p}
function setScene(i){SCENE=i|0}
function _sHex(h){h=String(h).replace('#','');
  if(h.length===3)h=h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
  return [parseInt(h.slice(0,2),16)||0,parseInt(h.slice(2,4),16)||0,
    parseInt(h.slice(4,6),16)||0]}
function _sHsl(r,g,b){r/=255;g/=255;b/=255;
  const mx=Math.max(r,g,b),mn=Math.min(r,g,b),l=(mx+mn)/2,d=mx-mn;
  let h=0,s=0;
  if(d>0){s=l>0.5?d/(2-mx-mn):d/(mx+mn);
    h=mx===r?((g-b)/d+(g<b?6:0)):mx===g?((b-r)/d+2):((r-g)/d+4);h/=6}
  return [h,s,l]}
function _sCh(p,q,t){if(t<0)t+=1;if(t>1)t-=1;
  if(t<1/6)return p+(q-p)*6*t;if(t<0.5)return q;
  if(t<2/3)return p+(q-p)*(2/3-t)*6;return p}
function _sRgb(h,s,l){if(s<=0){const v=Math.round(l*255);return [v,v,v]}
  const q=l<0.5?l*(1+s):l+s-l*s,p=2*l-q;
  return [Math.round(_sCh(p,q,h+1/3)*255),Math.round(_sCh(p,q,h)*255),
    Math.round(_sCh(p,q,h-1/3)*255)]}
function _sPair(v){return ('0'+Math.max(0,Math.min(255,v|0)).toString(16)).slice(-2)}
function sceneLum(hex){const c=_sHex(hex).map(v=>{v/=255;
  return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)});
  return 0.2126*c[0]+0.7152*c[1]+0.0722*c[2]}
function _sLumOf(h,s,l){const o=_sRgb(h,s,l);
  return sceneLum('#'+_sPair(o[0])+_sPair(o[1])+_sPair(o[2]))}
const _sCache={};
/* The step is taken in LUMINANCE, not in HSL lightness. Hue carries most of
   the brightness in sRGB - green at l=0.9 outshines magenta at l=0.9 - so a
   lightness offset would have let a green room outshine the climax on a
   light theme. Aiming at a luminance target and solving for l keeps
   "brightest scene last" true for every theme and every hue. */
function scenePaint(base){const key=SCENE+'|'+base;
  if(_sCache[key])return _sCache[key];
  const p=SPAL[SCENE]||SPAL[0]||[0,1,0];
  const c=_sHex(base),hsl=_sHsl(c[0],c[1],c[2]);
  const h=((hsl[0]+p[0]/360)%1+1)%1,s=Math.max(0,Math.min(1,hsl[1]*p[1]));
  const base_l=sceneLum(base),anc=sceneLum(SCENE_FLOOR);
  /* Which way the budget is spent depends on where the theme already sits.
     A dark theme has all its room above, so scenes brighten toward the
     climax. A light theme has almost none - brightening there squeezed
     three scenes into the same white - so the SAME numbers are mirrored:
     the quiet scenes darken and the climax, moving least, is still the
     brightest frame. The rule "the peak is last" survives either way. */
  let kmax=p[2];for(let i=0;i<SPAL.length;i++)kmax=Math.max(kmax,SPAL[i][2]);
  const k=anc>0.5?p[2]-kmax:p[2];
  const goal=Math.max(0,Math.min(1,k>=0?anc+k*(1-anc):anc*(1+k)));
  /* Every colour in the scene is moved by the same factor on (L + 0.05),
     which is exactly the quantity a WCAG contrast ratio is built from. So
     the wall keeps its value gap against the floor in every scene: the
     palette moves the whole frame, it does not flatten the terrain. An
     additive brighten did flatten it - floor-vs-wall fell to 1.04 at the
     altar, below the 1.18 the page ships with - which is why it is a ratio. */
  const mul=(goal+0.05)/(anc+0.05);
  const want=Math.max(0,Math.min(1,(base_l+0.05)*mul-0.05));
  let lo=0,hi=1,l=hsl[2];
  for(let i=0;i<18;i++){l=(lo+hi)/2;
    if(_sLumOf(h,s,l)<want)lo=l;else hi=l}
  const o=_sRgb(h,s,(lo+hi)/2);
  return _sCache[key]='#'+_sPair(o[0])+_sPair(o[1])+_sPair(o[2])}
/* Read the palette back off the page rather than off this source: what the
   scene is painted with is a fact about the running artifact. */
function sceneFacts(){const keep=SCENE,out=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;
    const f=scenePaint('SURFACE_TOKEN'),w=scenePaint('BORDER_TOKEN');
    out.push({floor:f,wall:w,lum:sceneLum(f),wallLum:sceneLum(w)})}
  SCENE=keep;return {scene:keep,scenes:out}}
"""

__all__ = [
    "ADVENTURE_PALETTE",
    "FISHING_PALETTE",
    "KAIJU_PALETTE",
    "MARBLE_PALETTE",
    "PLATFORMER_PALETTE",
    "RACING_PALETTE",
    "SHOOTER_PALETTE",
    "SCENE_PREAMBLE",
]
