"""The giant-boss fight - a scale this project had no way to express.

Every enemy SIDRA could generate was the player's own size and arrived in
quantity. The owner's viewing notes (`docs/research/game-design-notes.md` §6,
extracted from watching a 22-minute episode end to end) say scale is not a
sprite size but a set of rules, and all of them are reachable in canvas:

* **Observation 1 - hugeness is what you do not draw.** The monster is a leg,
  a claw and a tail crossing the frame; the whole body appears once, at the
  end. So this template *cannot* draw the body while the boss is alive:
  ``BODY`` only becomes true on the kill, and the probe checks it.
* **Observation 2 - weight is stride and dust.** The player's walker has a
  slow leg cycle and puts dust down on every footfall, and a hit reads in
  three beats: flash, lingering smoke, silhouette back out of the smoke.
* **Observation 3 - escalation has a shape.** Ground-cracks telegraph before
  they open, so the warning is playable rather than decorative.
* **Measured (§6 定量) - combat cuts every ~2.1 seconds.** At 60fps that is
  126 frames, and it is the interval this template schedules its attacks on:
  the film's rhythm ported as a number, not as a mood.

The fight is three cycles of one loop: shoot the leg until it buckles, the
head drops into reach, hit the exposed weak point, it recovers angrier. A
shot anywhere else is wasted, which is what makes the leg phase a decision
instead of a delay.

Token contract, shared with every template: ``SPEED_TOKEN`` is how fast the
cracks open, ``BAND_TOKEN`` the leg hits one cycle costs, ``SEED_TOKEN`` the
attack seed. ``REDUCED``/``FRAME`` come from the animation preamble - the
dust and the heat-haze freeze under reduced motion while the fight keeps
working - and ``sfx``/``shake``/``hitstop``/``burst`` from the audio and
juice preambles.
"""

from __future__ import annotations

#: Words that pick this template. ``ゴジラ`` is here on purpose: the genre is
#: buildable, so the request must *route*, and the title guard in
#: ``games.generate_game`` is what keeps the name off the artifact.
KAIJU_WORDS: tuple[str, ...] = (
    "怪獣",
    "かいじゅう",
    "カイジュウ",
    "巨大",
    "ボス戦",
    "巨獣",
    "kaiju",
    "ゴジラ",
    "ガメラ",
    "ウルトラマン",
    "godzilla",
    "titan",
)

#: (crack speed, leg hits per cycle).
KAIJU_DIFFICULTY: dict[str, tuple[float, float]] = {
    "easy": (0.9, 3),
    "normal": (1.4, 5),
    "hard": (2.1, 7),
}

KAIJU_TITLE = "巨獣迎撃戦"
KAIJU_HOW = (
    "← → で歩く、SPACE で撃つ。脚を撃ち抜くと頭が落ちてくる——そこだけが弱点。"
    "地面に走る線は地割れの予兆、来る前に離れる。3 周期で仕留める。"
    "R でやり直し、M で消音。"
)

#: 60fps × 2.1s. The measured combat cut length, used as the attack interval.
KAIJU_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const CRACK=SPEED_TOKEN,LEGHP=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const W=cv.width,H=cv.height,GROUND=H-46,BEAT=126;
let me,shots,boss,cracks,dust,t,state,cycles;
function reset(){
  /* Under the leg, not across the field (§8 事実 5): the first shot a
     new player fires has to hit something. Walking away is a choice
     they make after that, not a toll before it. */
  me={x:W*0.68,hp:3,step:0,cool:0};
  shots=[];cracks=[];dust=[];t=0;cycles=0;state='fight';
  boss={phase:'leg',legHp:LEGHP,head:-160,timer:BEAT,shown:false,hurt:0,smoke:0};}
setPal(KAIJU_PAL_TOKEN);
function legX(){return W*0.72+Math.sin(t/90)*26}
function fire(){if(state!=='fight')return;
  /* A press during the cooldown is kept, not dropped (§12, C-1311): one
     queued shot, fired the frame the cannon is ready. */
  if(me.cool>0){me.queued=true;return}
  me.cool=11;
  shots.push({x:me.x,y:GROUND-26,vy:-7});sfx('fire')}
function hitLeg(){boss.legHp--;boss.hurt=8;boss.smoke=34;shake(3);burst(legX(),GROUND-70,7,'ALERT_JUICE');
  sfx('cut');
  /* The leg buckling is the only way the head comes down. Three beats:
     flash, smoke that stays, silhouette back out of it (観察 2). */
  if(boss.legHp<=0){boss.phase='open';boss.head=GROUND-150;boss.timer=BEAT*2;
    hitstop(4);sfx('key')}}
function hitHead(){cycles++;boss.hurt=12;shake(7);burst(legX(),boss.head,16,'ACCENT_JUICE');
  hitstop(6);sfx('sword');
  if(cycles>=3){state='won';boss.shown=true;boss.phase='down';shake(10)}
  else{boss.phase='leg';boss.legHp=LEGHP;boss.head=-160;boss.timer=BEAT}}
function openCrack(){const x=60+rand()*(W-120);
  cracks.push({x:x,w:0,warn:34,open:0});sfx('charge')}
function step(){t++;
  combat(state==='fight'&&gateState()==='playing');
  if(state==='fight'){
    if(me.cool>0){me.cool--;
      if(me.cool===0&&me.queued){me.queued=false;fire()}}
    /* The shared steering part (C-1114), with this game's own margin. */
    partsSteerX(me,2.1,30,W-30);
    if(Math.abs(me.x-(me.lastX||me.x))>0.4){me.step+=0.05;
      /* Dust on the footfall, not every frame: weight is the stride. */
      if(Math.sin(me.step*6.283)>0.97)dust.push({x:me.x,y:GROUND,r:2,a:1})}
    me.lastX=me.x;
    boss.timer--;
    if(boss.timer<=0){boss.timer=BEAT;openCrack()}
    if(boss.hurt>0)boss.hurt--;
    if(boss.smoke>0)boss.smoke--;
    shots.forEach(s=>{s.y+=s.vy});
    shots=shots.filter(s=>{
      if(boss.phase==='open'&&Math.abs(s.x-legX())<46&&Math.abs(s.y-boss.head)<40){
        hitHead();return false}
      if(boss.phase==='leg'&&Math.abs(s.x-legX())<30&&s.y<GROUND-30&&s.y>GROUND-110){
        hitLeg();return false}
      return s.y>-20});
    cracks.forEach(c=>{if(c.warn>0){c.warn--;if(c.warn===0)sfx('clash')}
      else c.open=Math.min(56,c.open+CRACK)});
    cracks=cracks.filter(c=>{
      if(c.warn===0&&c.open>10&&Math.abs(c.x-me.x)<c.open*0.5+10){
        me.hp--;shake(6);sfx('hurt');hitstop(3);
        if(me.hp<=0){state='lost';failBeat(me.x,GROUND-20)}return false}
      return c.open<56});
    dust.forEach(d=>{d.r+=0.6;d.a-=0.03});dust=dust.filter(d=>d.a>0);}
  draw();requestAnimationFrame(step)}
function K(k){return keys[k]}
const keys={};
addEventListener('keydown',e=>{keys[e.key]=true;
  if(e.key===' '){fire();e.preventDefault()}
  if(e.key==='r'||e.key==='R')reset()});
addEventListener('keyup',e=>{keys[e.key]=false});
function bossFacts(){return{phase:boss.phase,cycles:cycles,shown:boss.shown,
  legHp:boss.legHp,beat:BEAT,state:state,hp:me.hp}}
function draw(){const now=performance.now();
  /* 埃 -> 閃光 -> 最大明度: the phase picks the air the fight happens in, and
     the brightest frame of the whole page is the one where it goes down
     (§7 観察 5-6). Mood only - the leg and the head still read by shape. */
  setScene(boss.phase==='leg'?0:boss.phase==='open'?1:2);
  cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(0,0,W,H);
  cx.fillStyle=scenePaint('RAISED_TOKEN');cx.fillRect(0,GROUND,W,H-GROUND);
  cracks.forEach(c=>{
    if(c.warn>0){cx.strokeStyle='MAGENTA_TOKEN';cx.lineWidth=2;
      cx.beginPath();cx.moveTo(c.x-16,GROUND+4);cx.lineTo(c.x+16,GROUND+4);cx.stroke()}
    else{cx.fillStyle='#05070f';cx.fillRect(c.x-c.open*0.5,GROUND,c.open,H-GROUND)}});
  dust.forEach(d=>{cx.fillStyle='#dfe7f5';cx.globalAlpha=d.a*0.5;
    cx.beginPath();cx.arc(d.x,d.y,d.r,0,6.283);cx.fill()});
  cx.globalAlpha=1;
  /* The monster is a leg and a tail crossing the frame. Never the body -
     until it is down, and then once. (観察 1) */
  const lx=legX();
  if(!boss.shown){
    cx.fillStyle=boss.hurt>0?'#dfe7f5':'BORDER_TOKEN';
    cx.beginPath();cx.moveTo(lx-34,0);cx.lineTo(lx+20,0);
    cx.lineTo(lx+30,GROUND);cx.lineTo(lx-44,GROUND);cx.closePath();cx.fill();
    cx.fillStyle='BORDER_TOKEN';
    cx.beginPath();cx.moveTo(W,GROUND-90);cx.lineTo(W,GROUND-30);
    cx.lineTo(lx+40,GROUND-6);cx.closePath();cx.fill();
    if(boss.smoke>0){cx.fillStyle='#dfe7f5';cx.globalAlpha=boss.smoke/70;
      cx.beginPath();cx.arc(lx,GROUND-70,40,0,6.283);cx.fill();cx.globalAlpha=1}
    if(boss.phase==='open'){
      cx.fillStyle=boss.hurt>0?'#dfe7f5':'MAGENTA_TOKEN';
      cx.beginPath();cx.arc(lx,boss.head,34,0,6.283);cx.fill();
      cx.fillStyle='ALERT_JUICE';cx.beginPath();cx.arc(lx,boss.head,12,0,6.283);cx.fill()}}
  else{cx.fillStyle='BORDER_TOKEN';
    cx.beginPath();cx.moveTo(lx-160,GROUND);cx.lineTo(lx-40,GROUND-120);
    cx.lineTo(lx+70,GROUND-96);cx.lineTo(lx+180,GROUND);cx.closePath();cx.fill()}
  const gait=Math.sin(me.step*6.283);
  cx.fillStyle='CYAN_TOKEN';cx.fillRect(me.x-16,GROUND-30,32,18);
  cx.fillRect(me.x-4,GROUND-42,8,12);
  cx.strokeStyle='CYAN_TOKEN';cx.lineWidth=3;
  [-10,10].forEach((o,i)=>{cx.beginPath();cx.moveTo(me.x+o,GROUND-14);
    cx.lineTo(me.x+o+(i?gait:-gait)*7,GROUND);cx.stroke()});
  shots.forEach(s=>{cx.fillStyle='ACCENT_JUICE';cx.fillRect(s.x-2,s.y-8,4,10)});
  cx.fillStyle='MAGENTA_TOKEN';
  for(let i=0;i<me.hp;i++){cx.fillRect(12+i*18,10,14,10)}
  cx.fillStyle='#dfe7f5';cx.font='13px ui-monospace,monospace';
  cx.fillText('周期 '+cycles+'/3  脚 '+Math.max(0,boss.legHp),W-190,19);
  if(state!=='fight'){cx.fillStyle='#05070fd0';cx.fillRect(0,0,W,H);
    cx.fillStyle='#dfe7f5';cx.font='20px ui-monospace,monospace';
    const a=state==='won'?'巨獣、沈黙。':'部隊は退いた。';
    cx.fillText(a,W/2-a.length*10,H/2-8);
    cx.font='13px ui-monospace,monospace';
    const b='R でもう一度';cx.fillText(b,W/2-b.length*6.5,H/2+18)}}
/* One tap from the result goes again (§8 事実 3). The keyboard restart
   above is the only one this template had, which on a phone meant the
   result screen was a dead end. */
cv.addEventListener('pointerdown',()=>{if(state!=='fight')reset()});
reset();step();
"""

#: The page driven in node: the browser is a no-op proxy, the real script
#: runs, and the fight is played through three cycles so the rules can be
#: read back instead of grepped for.
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const keyHandlers = [];
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') keyHandlers.push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn(i * 16) } }
/* Past the start screen: the gate holds every frame until pressed. */
const press = { key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} };
keyHandlers.forEach(fn => fn(press));
run(2);
/* Wasted shots first: hitting the leg while the head is down is the only
   thing that works, so shooting the sky must move nothing. */
const before = bossFacts();
for (let i = 0; i < 40; i++) { shots.push({x: 10, y: 40, vy: -7}); run(1) }
const afterMisses = bossFacts();
/* Now fight it properly: put a shot where the leg is, every frame, and read
   what the rules do. Records whether the body was ever drawn while alive. */
let bodyWhileAlive = false, sawOpen = false, cyclesAt = [];
for (let i = 0; i < 3000 && bossFacts().state === 'fight'; i++) {
  const f = bossFacts();
  if (f.shown && f.state === 'fight') bodyWhileAlive = true;
  if (f.phase === 'open') { sawOpen = true; shots.push({x: 0, y: 0, vy: 0}) }
  const aim = f.phase === 'open' ? -160 : -70;
  shots.push({x: Math.sin(i/90)*26 + 720*0.72, y: 320 - 46 + aim + 8, vy: 0});
  run(1);
  if (bossFacts().cycles !== f.cycles) cyclesAt.push(i);
}
const end = bossFacts();
const palette = sceneFacts();
console.log(JSON.stringify({
  scenes: palette.scenes,
  beat: end.beat, phaseStart: before.phase, legHpStart: before.legHp,
  cyclesAfterMisses: afterMisses.cycles, legHpAfterMisses: afterMisses.legHp,
  sawOpen: sawOpen, bodyWhileAlive: bodyWhileAlive,
  cycles: end.cycles, shown: end.shown, state: end.state, kills: cyclesAt.length,
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the fight can be played in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)



#: The queued shot, played (C-1311): a press during the cooldown fires the
#: frame the cannon is ready; a single press shoots exactly once.
QUEUE_PROBE = """
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
function key(k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(2);
/* The shot itself flies off and vanishes, so the cannon's own cooldown is
   the witness: a re-armed cooldown eleven frames after the first shot is
   the queued second shot firing. */
me.cool = 0; me.queued = false; shots.length = 0;
key(' ');
const afterFirst = shots.length, coolStart = me.cool;
run(3);
key(' ');
const keptQueue = me.queued === true;
run(9);
const coolAfterQueue = me.cool;
run(30); me.queued = false; me.cool = 0;
key(' ');
run(12);
const coolAfterSingle = me.cool, ghostQueue = me.queued === true;
console.log(JSON.stringify({ afterFirst: afterFirst, coolStart: coolStart,
  keptQueue: keptQueue, coolAfterQueue: coolAfterQueue,
  coolAfterSingle: coolAfterSingle, ghostQueue: ghostQueue }));
"""


def queue_probe(script: str) -> str:
    """The page's own script, wrapped so a queued shot can be watched."""

    return QUEUE_PROBE.replace("SCRIPT_PLACEHOLDER", script)

__all__ = [
    "QUEUE_PROBE",
    "queue_probe",
    "KAIJU_DIFFICULTY",
    "KAIJU_HOW",
    "KAIJU_SCRIPT",
    "KAIJU_TITLE",
    "KAIJU_WORDS",
    "PROBE",
    "probe_source",
]
