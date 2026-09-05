"""A fixed-camera 3D run, drawn without a 3D library.

§9 学び (5) asks for 3D, and the owner's direction points that way. C-1115
attaches one condition to it that decides the whole shape: **no external
CDN**. The artifact is one HTML file that talks to nothing, and a page that
fetches a renderer at load is a page that stops working the day the CDN
does.

That leaves two ways to get 3D, and the item asks for the verification, so
here it is:

* **Bundle a library.** three.js minified is roughly 600KB. A generated
  page is currently ~47KB, so every artifact would grow about fourteen
  times - to carry a scene graph, a material system, loaders and a WebGL
  backend, for one fixed camera pointed down a corridor. It would also put
  a vendored third-party copy in the tree that nothing else needs.
* **Project the points.** A fixed camera is the case where the maths is
  small: divide by depth, sort back to front, draw. That is about a
  hundred lines on the 2D context the other nine templates already use,
  and it inherits every shared preamble for free - the round clock, the
  failure beat, the result strip, the panel, the skins.

The second is what this is, and the choice is not a compromise: for a
fixed camera there is nothing in three.js this game would call. What the
page gives up is everything a moving camera needs - and full 3D generation
is explicitly out of scope (§9 事実 1: unsolved even in Genie 3).

The game is the plainest 3D thing there is, on purpose: a marble rolls
down a corridor, the player steers left and right, gates are scored and
blocks are not. Steering goes through the shared part from C-1114, which
is the first time a mechanic written for one template has been reused by
a template written after it.
"""

from __future__ import annotations

import json

MARBLE_TITLE = "転がる玉のコース"
MARBLE_HOW = "← → で玉を寄せる。ゲートを抜けると加点、ブロックに当たると転倒。"

#: Words that should land here. 3D is the one people type; the rest are
#: what they call the thing when they do not.
MARBLE_WORDS: tuple[str, ...] = (
    "3d",
    "３ｄ",
    "立体",
    "奥行き",
    "転がる",
    "転がす",
    "ころがる",
    "玉転がし",
    "ボール転がし",
    "マーブル",
)

#: What one gate pays before any multiplier. Named in Python so the
#: instrument reads the same number the page does rather than a copy of it
#: that can drift (C-1421; C-1420 needs it for the same reason).
GATE_BASE = 1

MARBLE_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const ROLL=SPEED_TOKEN,GATEW=BAND_TOKEN,SEED=SEED_TOKEN;
/* What one gate is worth before any multiplier. The hot gate is this
   again on top (C-1313's double), added outside the run's multiplier. */
const GATE_BASE=GATE_BASE_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const W=cv.width,H=cv.height;
/* The whole camera: eye height, focal length, and how far ahead the world
   is drawn. A fixed camera means these never change, which is exactly why
   a hundred lines is enough (C-1115). */
const EYE=26,FOV=520,FAR=900,NEAR=12,LANE=120;
/* §6 観察 3 (C-1314): the course re-accelerates by thirds - the same
   multipliers the shooter's acts use - so the brightest sky (C-1307) is
   also the fastest stretch, and the crescendo is in the roll, not only
   in the paint. */
const ACT_ROLL=[1,1.15,1.3];
function actOf(){return ball.z>=COURSE*2/3?2:ball.z>=COURSE/3?1:0}
function rollNow(){return ROLL*ACT_ROLL[actOf()]}
setPal(MARBLE_PAL_TOKEN);
/* HUD contract (§4 WCAG 1.4.3, C-1334): draw() paints the HUD through
   these constants and hudFacts() reports them, so the metric can blend
   the plate over every measured sky the way the canvas does. The plate
   is the untinted theme surface at 0.7: the brightest final act was
   sinking the themed ink to ~3:1 here too (C-1329's fix, more templates). */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A}}
let ball,things,gates,score,hotTaken,hotTotal,state,t,over,COURSE=1;
/* World to screen. z is depth ahead of the camera; y is up. Everything
   drawn here goes through this one function, so "3D" is this line. */
function proj(x,y,z){const d=Math.max(NEAR,z);
  return {x:W/2+x*FOV/d,y:H*0.62-(y-EYE)*FOV/d,s:FOV/d}}
function reset(){ball={x:0,y:8,z:0,vx:0};gates=0;score=0;hotTaken=0;hotTotal=0;
  t=0;state='roll';over='';
  rs=(SEED>>>0)||1;things=[];
  /* A gate first and close, so the opening hands something over before it
     asks for anything (§8 事実 5). Fixed at the middle it was not a gift at
     all: a player who has wandered - which is what a new player does - is
     nowhere near the middle by the time they reach it, and C-1108's masher
     measured exactly 0. It comes to *them* instead; everything after it is
     steering, as it should be. */
  things.push({z:150,kind:'gate',x:0,first:true});
  for(let i=1;i<26;i++){const z=150+i*130;
    if(rand()<0.42){things.push({z:z,kind:'block',x:(rand()*2-1)*(LANE-26)})}
    things.push({z:z+65,kind:'gate',x:(rand()*2-1)*(LANE-GATEW)})}
  /* The whole run, in world units: distance is this course's scene. */
  COURSE=things[things.length-1].z+80;
  /* The optional danger (§13 事実 1, C-1313): a gate standing in a block's
     shadow - close behind it, close beside it - pays double. Reaching it
     means swerving around the block and back; skipping it costs nothing
     but the points. The opening gift gate is never hot: a present with a
     price on it is not a present. */
  things.forEach(o=>{if(o.kind!=='gate'||o.first)return;
    o.hot=things.some(b=>b.kind==='block'&&o.z-b.z>0&&o.z-b.z<160&&
      Math.abs(b.x-o.x)<95);
    if(o.hot)hotTotal++})}
reset();
addEventListener('keydown',e=>{
  if(e.key==='ArrowLeft'||e.key==='ArrowRight')e.preventDefault();
  if(e.key==='r'||e.key==='R')reset()});
cv.addEventListener('pointerdown',()=>{if(state!=='roll'){reset()}});
function shade(hex,k){const n=parseInt(hex.slice(1),16);
  const r=Math.round(((n>>16)&255)*k),g=Math.round(((n>>8)&255)*k),b=Math.round((n&255)*k);
  return 'rgb('+r+','+g+','+b+')'}
function step(){
  if(state==='roll'){t++;
    /* The shared steering part (C-1114), in world units rather than
       pixels: the part does not care which space it is moving in. */
    partsSteerX(ball,3.4,-LANE+14,LANE-14);
    ball.z+=rollNow();
    /* Where we were, at this point down the corridor (C-1412). z is the
       course, so a faster roll stays in step with the trail. */
    ghostSample(ball.z,ball.x);
    /* Roll: the marble bobs a little so the depth reads as motion. */
    ball.y=8+Math.sin(t*0.18)*1.6;
    things.forEach(o=>{if(o.done)return;
      const dz=o.z-ball.z;
      /* The first gate lines itself up while it is still ahead. */
      if(o.first&&dz<90){o.x=ball.x}
      if(dz<0&&dz>-rollNow()-6){o.done=true;
        if(o.kind==='gate'){
          if(Math.abs(o.x-ball.x)<GATEW){gates++;
            /* The run's multiplier, asked once (C-1420). It rides the
               gate's base value and nothing else: the hot gate's extra is
               added *outside* it, so the top payment reads as
               「base x mult + base」 rather than as base x 2 x mult. Two
               multipliers stacked would make the best line on the course
               the one nobody can work out from the seat, which is the
               opposite of §13's readable risk. Same shape as C-1411's
               choice to add the graze rather than multiply it. */
            const pay=comboHit();
            /* The risk pays in points AND in feel: the hot gate rings a
               brighter bell and kicks the camera harder (§13: the reward
               has to change the play, not decorate it). */
            if(o.hot){score+=scorePop(proj(o.x,10,NEAR+40).x,H*0.55,pay+GATE_BASE);
              hotTaken++;sfx('key');shake(4);
              burst(proj(o.x,10,NEAR+40).x,H*0.55,16,'ALERT_JUICE')}
            else{score+=scorePop(proj(o.x,10,NEAR+40).x,H*0.55,pay);
              sfx('catch');shake(2);
              burst(proj(o.x,10,NEAR+40).x,H*0.55,10,'ACCENT_JUICE')}}
          /* Through the posts or past them: a gate that went by outside
             them is the miss this run is broken by. marble has no fall -
             the entry said 「落下」 but the only way out of the corridor is
             a block, which ends the go outright. A gate missed is what a
             player can do wrong and keep playing. */
          else{comboMiss()}}
        else if(Math.abs(o.x-ball.x)<24){state='over';over='ブロックに当たった。';
          comboMiss();failBeat(W/2,H*0.6)}}});
    if(things.every(o=>o.done)){state='over';over='コースを走り切った。';
      winBeat(W/2,H*0.5)}}
  /* A straight corridor's scene is distance (§7 観察 5-6, C-1307): the sky,
     the horizon band and the rails step once per third of the course, and
     the final stretch is rolled at under the brightest sky of the run.
     Gates and blocks keep their information colours (§4). */
  setScene(actOf());
  /* Painter's algorithm: far things first, near things over them. That
     ordering *is* the depth - there is no buffer to test against. */
  const sky=scenePaint('SURFACE_TOKEN');
  cx.fillStyle=sky;cx.fillRect(0,0,W,H);
  const horizon=proj(0,0,FAR);
  cx.fillStyle=shade(scenePaint('BG_TOKEN'),1);cx.fillRect(0,0,W,horizon.y);
  /* The floor, as receding rails and rungs. Perspective is doing all of
     the work; nothing here is a texture. */
  cx.strokeStyle=shade(scenePaint('BORDER_TOKEN'),1);cx.lineWidth=1;
  for(const side of [-LANE,LANE]){cx.beginPath();
    const a=proj(side,0,NEAR),b=proj(side,0,FAR);
    cx.moveTo(a.x,a.y);cx.lineTo(b.x,b.y);cx.stroke()}
  const first=Math.ceil(ball.z/60)*60;
  for(let z=first;z<ball.z+FAR;z+=60){const d=z-ball.z;
    const a=proj(-LANE,0,d),b=proj(LANE,0,d);
    cx.globalAlpha=Math.max(0.08,1-d/FAR);cx.beginPath();
    cx.moveTo(a.x,a.y);cx.lineTo(b.x,b.y);cx.stroke()}
  cx.globalAlpha=1;
  const ahead=things.filter(o=>!o.done&&o.z-ball.z<FAR&&o.z-ball.z>NEAR)
    .sort((p,q)=>q.z-p.z);
  ahead.forEach(o=>{const d=o.z-ball.z,p=proj(o.x,0,d),k=Math.max(0.25,1-d/FAR);
    if(o.kind==='gate'){const half=GATEW*p.s,top=proj(o.x,44,d);
      cx.strokeStyle=shade(TUNE_ACCENT,k);cx.lineWidth=Math.max(1,3*p.s);
      cx.beginPath();cx.moveTo(p.x-half,p.y);cx.lineTo(p.x-half,top.y);
      cx.lineTo(p.x+half,top.y);cx.lineTo(p.x+half,p.y);cx.stroke();
      /* Worth double, and it says so by FORM (§4): a second inner frame
         and a diamond at the apex, not a colour swap. */
      if(o.hot){const h2=half*0.8;
        cx.beginPath();cx.moveTo(p.x-h2,p.y);cx.lineTo(p.x-h2,top.y+4*p.s);
        cx.lineTo(p.x+h2,top.y+4*p.s);cx.lineTo(p.x+h2,p.y);cx.stroke();
        const r=Math.max(2,6*p.s);
        cx.beginPath();cx.moveTo(p.x,top.y-r);cx.lineTo(p.x+r,top.y);
        cx.lineTo(p.x,top.y+r);cx.lineTo(p.x-r,top.y);cx.closePath();
        cx.fillStyle=shade(TUNE_ACCENT,k);cx.fill()}}
    else{const w=26*p.s,h=30*p.s;
      cx.fillStyle=shade('MAGENTA_TOKEN',k);
      cx.fillRect(p.x-w,p.y-h,w*2,h);
      cx.fillStyle=shade('MAGENTA_TOKEN',k*0.6);
      cx.fillRect(p.x-w,p.y-h,w*2,4)}});
  /* The past self, at this point down the corridor: drawn and nothing
     else - no collision, no score, no sound (C-1401's contract, wired to
     its second template by C-1412). Placed at the marble's own depth so
     the two are compared where the player is looking, and under it so the
     present is never hidden by the past. */
  /* The second ghost (§11, C-1335): the run before this one, an
     outline at the marble's own depth, under the best so the record
     stays on top - and one body when the last run IS the record. */
  const glz=ghostAtLast(ball.z);
  if(glz!==null){const lp=proj(glz,8,NEAR+34),lr=13*lp.s;
    cx.save();cx.globalAlpha=0.35;
    cx.strokeStyle=shade(TUNE_ACCENT,0.9);cx.lineWidth=1;
    cx.beginPath();cx.arc(lp.x,lp.y,lr,0,6.2832);cx.stroke();cx.restore()}
  const gx=ghostAt(ball.z);
  if(gx!==null){const gp=proj(gx,8,NEAR+34),gr=13*gp.s;
    cx.save();cx.globalAlpha=0.32;
    cx.fillStyle=shade(TUNE_ACCENT,0.55);cx.beginPath();
    cx.arc(gp.x,gp.y,gr,0,6.2832);cx.fill();
    cx.globalAlpha=0.6;cx.strokeStyle=shade(TUNE_ACCENT,1);cx.lineWidth=1;
    cx.beginPath();cx.arc(gp.x,gp.y,gr,0,6.2832);cx.stroke();cx.restore()}
  /* The marble last: it is the nearest thing there is. */
  const bp=proj(ball.x,ball.y,NEAR+34),br=13*bp.s;
  cx.fillStyle='#00000044';cx.beginPath();
  cx.ellipse(bp.x,proj(ball.x,0,NEAR+34).y,br*1.1,br*0.4,0,0,6.2832);cx.fill();
  /* Drawn, not pasted. The marble's shading is the depth cue - the lit
     side is where the light is, and it moves as the ball crosses the
     corridor - so a flat image would be the one thing on screen that did
     not agree with the perspective. Declared as having no sprite slot for
     that reason (C-1116's contract), like the duel's fighters. */
  cx.fillStyle=shade(TUNE_ACCENT,0.55);cx.beginPath();
  cx.arc(bp.x,bp.y,br,0,6.2832);cx.fill();
  cx.fillStyle=shade(TUNE_ACCENT,1);cx.beginPath();
  cx.arc(bp.x-br*0.28,bp.y-br*0.3,br*0.62,0,6.2832);cx.fill();
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(32,12,330,24);cx.globalAlpha=1;
  cx.fillStyle=HUD_INK;cx.font='13px ui-monospace,monospace';
  cx.fillText('スコア '+score+' '+comboLabel()+'  ゲート '+gates
    +'  距離 '+Math.round(ball.z),40,30);
  if(state!=='roll'){cx.fillStyle='SCRIM_TOKEN'+'cc';cx.fillRect(0,H/2-40,W,80);
    cx.fillStyle='INK_TOKEN';cx.textAlign='center';
    cx.font='20px ui-monospace,monospace';cx.fillText(over,W/2,H/2-6);
    cx.font='13px ui-monospace,monospace';
    cx.fillText('R / タップでもう一度',W/2,H/2+24);cx.textAlign='left'}
  requestAnimationFrame(step)}
/* Read back off the running page: where the run is, which act the sky is
   in, and the next thing ahead, so a probe can roll the course by hand. */
function marbleFacts(){let next=null;
  things.forEach(o=>{if(o.done||next)return;
    if(o.z-ball.z>0)next={kind:o.kind,x:o.x,dz:o.z-ball.z}});
  return {state:state,z:ball.z,x:ball.x,spd:rollNow(),gates:gates,score:score,
    ghost:ghostFacts(),
    hotTotal:hotTotal,hotTaken:hotTaken,scene:SCENE,
    course:COURSE,next:next}}
step();
"""

#: The page rolled in node: the same no-op browser the other probes build.
#: The pilot steers at gates and away from blocks, and notes the act of
#: the sky as each third of the course passes under the marble.
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function key(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
key('keydown', ' '); key('keyup', ' ');
run(2);
const early = marbleFacts();
let sceneMid = null, frames = 0;
/* The crescendo, measured: distance covered and frames spent, per act. */
const actZ = [0, 0, 0], actF = [0, 0, 0];
let lastZ = early.z;
while (marbleFacts().state === 'roll' && frames++ < 6000) {
  const f = marbleFacts();
  actZ[f.scene] += f.z - lastZ; actF[f.scene]++; lastZ = f.z;
  if (sceneMid === null && f.z > f.course / 3 + 60 && f.z < f.course * 2 / 3) sceneMid = f.scene;
  key('keyup', 'ArrowLeft'); key('keyup', 'ArrowRight');
  let aim = null;
  if (f.next) {
    /* Away from a block, into a gate. */
    aim = f.next.kind === 'block'
      ? (f.next.x >= f.x ? f.next.x - 60 : f.next.x + 60)
      : f.next.x;
  }
  if (aim !== null && aim < f.x - 3) key('keydown', 'ArrowLeft');
  else if (aim !== null && aim > f.x + 3) key('keydown', 'ArrowRight');
  run(1);
}
const end = marbleFacts();
const palette = sceneFacts();
const hud = hudFacts();
console.log(JSON.stringify({
  scenes: palette.scenes,
  hud: hud,
  sceneEarly: early.scene, sceneMid: sceneMid, sceneLate: end.scene,
  state: end.state, z: end.z, course: end.course, gates: end.gates,
  score: end.score, hotTotal: end.hotTotal, hotTaken: end.hotTaken,
  rates: actZ.map((z, i) => actF[i] ? z / actF[i] : 0),
  winBeats: winBeats(), failBeats: failBeats(),
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the course can be rolled in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The ghost probe (C-1412). The scene probe above rolls one course; this
#: one rolls two, with a browser that remembers between them, and records
#: where the marble went and where the ghost was drawn. ``roll`` overrides
#: the speed the way the panel does, because the claim worth checking is
#: the one the shared judge cannot make: the trail is indexed by z down
#: the corridor, so a *faster* run still meets its past self at the same
#: place on the course rather than at the same frame.
GHOST_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
const store = STORED_INPUT;
globalThis.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v) },
  removeItem: (k) => { delete store[k] } };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function key(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e)) }
key('keydown', ' '); key('keyup', ' ');
run(2);
/* Where the marble went, and where the ghost was drawn, frame by frame. */
const path = [], seen = [];
let frames = 0;
while (marbleFacts().state === 'roll' && frames++ < 6000) {
  const f = marbleFacts();
  path.push([Math.round(f.z), Math.round(f.x)]);
  if (f.ghost.last) seen.push([f.ghost.last[0], f.ghost.last[1]]);
  key('keyup', 'ArrowLeft'); key('keyup', 'ArrowRight');
  let aim = null;
  if (f.next) {
    aim = f.next.kind === 'block'
      ? (f.next.x >= f.x ? f.next.x - 60 : f.next.x + 60)
      : f.next.x }
  if (aim !== null && aim < f.x - 3) key('keydown', 'ArrowLeft');
  else if (aim !== null && aim > f.x + 3) key('keydown', 'ArrowRight');
  run(1) }
/* Past the end of the round, so roundBank has a chance to write. */
run(240);
const end = marbleFacts();
console.log(JSON.stringify({ path: path, seen: seen, frames: frames,
  ghost: end.ghost, z: end.z, score: end.score, state: end.state,
  spd: end.spd, trail: store['sidra.ghost.marble'] || null }));
"""


def ghost_probe_source(
    script: str, *, stored: dict | None = None, roll: float | None = None
) -> str:
    """Roll the corridor with a browser that remembers, at a chosen speed."""

    seeded = dict(stored or {})
    if roll is not None:
        tune = dict(seeded.get("sidra.tune.marble") or {})
        tune["speed"] = roll
        seeded["sidra.tune.marble"] = tune
    packed = {
        key: (value if isinstance(value, str) else json.dumps(value))
        for key, value in seeded.items()
    }
    return GHOST_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "STORED_INPUT", json.dumps(packed)
    )


__all__ = [
    "MARBLE_HOW",
    "MARBLE_SCRIPT",
    "MARBLE_TITLE",
    "MARBLE_WORDS",
    "PROBE",
    "GHOST_PROBE",
    "ghost_probe_source",
    "probe_source",
]

#: Rolls the real corridor two ways, so what the multiplier does is read
#: off a page that played. ``run`` steers through every gate it can reach;
#: ``skip`` deliberately swerves away from every third one, which is the
#: only way to see a run break without ending the go.
#:
#: The marble is steered by pressing the arrow keys the template listens
#: for - never by writing to ``ball.x`` - so the probe can only reach lines
#: a person could drive.
COMBO_PROBE = """
const mbNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : mbNothing),
  apply: () => mbNothing, set: () => true });
const mbHandlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT, addEventListener(){}, addListener(){} });
let mbClock = 0;
globalThis.performance = { now: () => mbClock };
globalThis.addEventListener = (type, fn) => { (mbHandlers[type] = mbHandlers[type] || []).push(fn) };
globalThis.Image = function(){ return mbNothing };
const mbStore = {};
globalThis.localStorage = { getItem: (k) => (k in mbStore ? mbStore[k] : null),
  setItem: (k, v) => { mbStore[k] = String(v) }, removeItem: (k) => { delete mbStore[k] } };
globalThis.location = { reload: () => {} };
globalThis.KeyboardEvent = function(type, init){ return Object.assign({ type: type }, init) };
globalThis.dispatchEvent = (ev) => { (mbHandlers[ev.type] || []).forEach(fn => fn(ev)); return true };
/* A recorder, so 「the multiplier is on screen the whole time」 is a claim
   about paint rather than about a function returning a string. */
let mbPaint = [];
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => mbNothing, querySelector: () => null,
  getElementById: () => ({ width: 720, height: 320, style: {},
    addEventListener: () => {},
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => new Proxy({
      fillText: (s) => { mbPaint.push(String(s)) }, fillRect: () => {} }, {
      get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : mbNothing)),
      set: () => true }) }) };
let mbQueued = null;
globalThis.requestAnimationFrame = (fn) => { mbQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
const MODE = MODE_INPUT;
let mbFrame = 0;
function mbKey(type, k){ (mbHandlers[type] || []).forEach(fn => fn({ key: k, code: k,
  preventDefault(){}, stopImmediatePropagation(){} })) }
mbKey('keydown', ' '); mbKey('keyup', ' ');
function mbStep(){ if (!mbQueued) return false;
  const fn = mbQueued; mbQueued = null; mbPaint = []; mbClock += 50 / 3;
  fn(mbFrame++ * 16); return true }
mbStep(); mbStep();
/* Which gates this run intends to miss. Counted rather than chosen by
   position, so the same gates are skipped whatever the course looks like. */
let mbSeenGates = 0;
/* The next of each kind, read off the page's own course. marbleFacts().next
   is whatever comes first, gate or block - steering at that drives into the
   blocks, which ends the go two gates in and measures nothing. */
function mbAhead(kind, within){ let best = null;
  things.forEach(o => { if (o.done || o.kind !== kind) return;
    const dz = o.z - ball.z;
    if (dz <= 0 || dz > within) return;
    if (!best || dz < best.dz) best = { x: o.x, dz: dz } });
  return best }
function mbWant(){
  /* A block close enough to matter comes first: no run is worth the go. */
  const block = mbAhead('block', 150);
  if (block && Math.abs(block.x - ball.x) < 46) {
    return block.x + (block.x < 0 ? 90 : -90) }
  const gate = mbAhead('gate', 900);
  if (!gate) return null;
  if (MODE === 'skip' && (mbSeenGates % 3) === 2) {
    /* Far enough off the line to pass outside the posts, but still on the
       course - a miss, not a crash. */
    return gate.x + (gate.x < 0 ? 120 : -120) }
  return gate.x }
const events = [];
let before = { score: 0, gates: 0, hot: 0, mult: 1, run: 0 };
for (let f = 0; f < FRAMES_INPUT; f++) {
  const want = mbWant();
  if (want !== null) { const gap = want - marbleFacts().x;
    if (gap < -1) { mbKey('keydown', 'ArrowLeft'); mbKey('keyup', 'ArrowRight') }
    else if (gap > 1) { mbKey('keydown', 'ArrowRight'); mbKey('keyup', 'ArrowLeft') }
    else { mbKey('keyup', 'ArrowLeft'); mbKey('keyup', 'ArrowRight') } }
  const seenBefore = marbleFacts();
  if (!mbStep()) break;
  const now = marbleFacts();
  /* x1 for every gate where no ladder is wired at all - which is what
     makes the new identity provably the old one until one is (C-1421). */
  const combo = mbCombo();
  /* A gate went by: either through the posts (the score moved) or past
     them (the run was taken). Both are events this is about. */
  const passed = now.gates !== seenBefore.gates;
  /* A run that got shorter without a gate going through the posts is a
     gate that went past them. Detected on the run rather than on the
     multiplier: a miss at x1 resets a run of two to nothing and moves no
     multiplier at all, and that is still the rule doing its job. */
  const missed = !passed && combo.run < before.run;
  if (passed || missed) {
    if (passed) { mbSeenGates++ }
    events.push({ f: f, kind: passed ? 'through' : 'past',
      paid: now.score - before.score,
      hot: now.hotTaken !== before.hot,
      mult: combo.mult, run: combo.run,
      /* What the HUD said on this very frame. */
      hud: mbPaint.filter(s => s.indexOf('スコア') === 0)[0] || null });
  }
  before = { score: now.score, gates: now.gates, hot: now.hotTaken,
    mult: combo.mult, run: combo.run };
  if (now.state !== 'roll') break;
}
const facts = marbleFacts();
function mbCombo(){ return (typeof comboFacts === 'function')
  ? comboFacts() : { run: 0, mult: 1, step: 0, max: 1 } }
console.log(JSON.stringify({ mode: MODE, events: events, combo: mbCombo(),
  score: facts.score, gates: facts.gates,
  hotTaken: facts.hotTaken, hotTotal: facts.hotTotal,
  state: facts.state, frames: mbFrame,
  hud: mbPaint.filter(s => s.indexOf('スコア') === 0)[0] || null }));
"""


def combo_probe_source(
    script: str, *, mode: str = "run", frames: int = 4000, reduced: bool = False
) -> str:
    """The page's own script, wrapped so the corridor can be driven in node."""

    return (
        COMBO_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("MODE_INPUT", json.dumps(mode))
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
    )
