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

MARBLE_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const ROLL=SPEED_TOKEN,GATEW=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const W=cv.width,H=cv.height;
/* The whole camera: eye height, focal length, and how far ahead the world
   is drawn. A fixed camera means these never change, which is exactly why
   a hundred lines is enough (C-1115). */
const EYE=26,FOV=520,FAR=900,NEAR=12,LANE=120;
setPal(MARBLE_PAL_TOKEN);
let ball,things,gates,state,t,over,COURSE=1;
/* World to screen. z is depth ahead of the camera; y is up. Everything
   drawn here goes through this one function, so "3D" is this line. */
function proj(x,y,z){const d=Math.max(NEAR,z);
  return {x:W/2+x*FOV/d,y:H*0.62-(y-EYE)*FOV/d,s:FOV/d}}
function reset(){ball={x:0,y:8,z:0,vx:0};gates=0;t=0;state='roll';over='';
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
  COURSE=things[things.length-1].z+80}
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
    ball.z+=ROLL;
    /* Roll: the marble bobs a little so the depth reads as motion. */
    ball.y=8+Math.sin(t*0.18)*1.6;
    things.forEach(o=>{if(o.done)return;
      const dz=o.z-ball.z;
      /* The first gate lines itself up while it is still ahead. */
      if(o.first&&dz<90){o.x=ball.x}
      if(dz<0&&dz>-ROLL-6){o.done=true;
        if(o.kind==='gate'){
          if(Math.abs(o.x-ball.x)<GATEW){gates++;sfx('catch');
            shake(2);burst(proj(o.x,10,NEAR+40).x,H*0.55,10,'ACCENT_JUICE')}}
        else if(Math.abs(o.x-ball.x)<24){state='over';over='ブロックに当たった。';
          failBeat(W/2,H*0.6)}}});
    if(things.every(o=>o.done)){state='over';over='コースを走り切った。'}}
  /* A straight corridor's scene is distance (§7 観察 5-6, C-1307): the sky,
     the horizon band and the rails step once per third of the course, and
     the final stretch is rolled at under the brightest sky of the run.
     Gates and blocks keep their information colours (§4). */
  setScene(ball.z>=COURSE*2/3?2:ball.z>=COURSE/3?1:0);
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
      cx.lineTo(p.x+half,top.y);cx.lineTo(p.x+half,p.y);cx.stroke()}
    else{const w=26*p.s,h=30*p.s;
      cx.fillStyle=shade('MAGENTA_TOKEN',k);
      cx.fillRect(p.x-w,p.y-h,w*2,h);
      cx.fillStyle=shade('MAGENTA_TOKEN',k*0.6);
      cx.fillRect(p.x-w,p.y-h,w*2,4)}});
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
  cx.fillStyle='#dfe7f5';cx.font='13px ui-monospace,monospace';
  cx.fillText('ゲート '+gates+'  距離 '+Math.round(ball.z),40,30);
  if(state!=='roll'){cx.fillStyle='#05070fcc';cx.fillRect(0,H/2-40,W,80);
    cx.fillStyle='#dfe7f5';cx.textAlign='center';
    cx.font='20px ui-monospace,monospace';cx.fillText(over,W/2,H/2-6);
    cx.font='13px ui-monospace,monospace';
    cx.fillText('R / タップでもう一度',W/2,H/2+24);cx.textAlign='left'}
  requestAnimationFrame(step)}
/* Read back off the running page: where the run is, which act the sky is
   in, and the next thing ahead, so a probe can roll the course by hand. */
function marbleFacts(){let next=null;
  things.forEach(o=>{if(o.done||next)return;
    if(o.z-ball.z>0)next={kind:o.kind,x:o.x,dz:o.z-ball.z}});
  return {state:state,z:ball.z,x:ball.x,gates:gates,scene:SCENE,
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
while (marbleFacts().state === 'roll' && frames++ < 6000) {
  const f = marbleFacts();
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
console.log(JSON.stringify({
  scenes: palette.scenes,
  sceneEarly: early.scene, sceneMid: sceneMid, sceneLate: end.scene,
  state: end.state, z: end.z, course: end.course, gates: end.gates,
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the course can be rolled in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = [
    "MARBLE_HOW",
    "MARBLE_SCRIPT",
    "MARBLE_TITLE",
    "MARBLE_WORDS",
    "PROBE",
    "probe_source",
]
