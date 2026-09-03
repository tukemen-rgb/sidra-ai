"""The race - the first template whose opponent is the clock, not a foe.

「レース」 sat on the apology side of the genre table: the word routed, the
honesty machinery named the gap, and the operator got a fishing game with a
caveat. The smallest race that is actually a race, buildable in canvas with
the shared preambles, is: a road that scrolls, a car that steers, obstacles
that cost speed, and three counted laps with a time each. The rules that make
it one, and the notes they come from:

* **Losing speed, not the run.** Contact with an obstacle and driving off the
  road both cut the pace and neither ends anything - a clipped corner costs
  seconds, which is what a lap timer is for. An instant fail would make the
  timer decoration.
* **The course is a function, not an array.** ``roadAt(d)`` maps distance to
  the road's centre through two seeded sines, so the same request bends the
  same way on every machine and a probe can ask where the road is without
  scrolling anything. ``SEED`` moves the phases and the obstacle spacing.
* **A lap is a scene (§7 観察 5-6).** The palette steps once per lap and the
  final lap is the brightest frame of the run - brightness spent on the
  climax, not on every frame. Mood only: the road edge, the obstacles and
  the off-road state all read by shape and text (§4 - never colour alone).
* **No fight, no combat step.** ``combat(true)`` raises the audio gain for
  fights (§6 観察 4); a race has none, so this template never calls it. The
  quiet templates are what make the loud ones read as loud.

Token contract, shared with every template: ``SPEED_TOKEN`` is the base pace
in course units per frame, ``BAND_TOKEN`` the minimum gap between obstacles
in course units, ``SEED_TOKEN`` the course seed. ``sfx``/``shake``/
``hitstop``/``burst`` come from the audio and juice preambles;
``setPal``/``setScene``/``scenePaint`` from the scene preamble.
"""

from __future__ import annotations

#: Words that pick this template. The genre table (`games._GENRES`) already
#: promised these; landing the template is what flips its answer to
#: "supported" without anyone editing the table.
RACING_WORDS: tuple[str, ...] = (
    "レース",
    "レーシング",
    "racing",
    "race",
    "サーキット",
    "周回",
)

#: (base pace in course units per frame, minimum obstacle gap in course
#: units). Hard is faster *and* denser: more road per second and less of it
#: empty, so the same three laps ask for more steering.
#:
#: Easy is 2.4, and C-1402 measured what that means against C-1104's
#: sixty-second clock: three laps take about 64 seconds, so the gentlest
#: setting is the one nobody finishes - two laps and a buzzer. Raising it
#: to 2.8 fixes that and takes away racing's only losing path (every rung
#: then beats the clock, and nothing else here can be lost), which is a
#: change to what this template *is*. Filed as C-1404 rather than decided
#: inside an unrelated item; the measurement is in that entry.
RACING_DIFFICULTY: dict[str, tuple[float, float]] = {
    "easy": (2.4, 260),
    "normal": (3.0, 190),
    "hard": (3.7, 130),
}

RACING_TITLE = "ひかりのサーキット"
RACING_HOW = (
    "← → でハンドルを切る。コース外と障害物は減速（走りは止まらない）。"
    "3 周でゴール、周回ごとのタイムが残る。R でやり直し、M で消音。"
)

RACING_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const PACE=SPEED_TOKEN,GAP=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const W=cv.width,H=cv.height,CARY=H-56,LAP=1800,LAPS=3,ROADW=190;
/* The course is a function of distance, not a stored array: the same SEED
   bends the same way everywhere, and the probe can ask where the road is.
   The two periods keep the worst drift per frame below the steering speed,
   so the road is always followable at every difficulty. */
const PH1=rand()*6.283,PH2=rand()*6.283;
function roadAt(d){return W/2+Math.sin(d/380+PH1)*150+Math.sin(d/151+PH2)*62}
let car,obs,dist,lap,lapT,times,state,grace,spd,nextObs,passed;
function reset(){car={x:roadAt(0)};obs=[];dist=0;lap=1;lapT=0;times=[];
  state='race';grace=0;spd=PACE;nextObs=320;passed=0}
setPal(RACING_PAL_TOKEN);
function onRoad(){return Math.abs(car.x-roadAt(dist))<ROADW/2-8}
function raceFacts(){return{state:state,lap:lap,laps:LAPS,dist:dist,spd:spd,passed:passed,
  base:PACE,carX:car.x,road:roadAt(dist),roadW:ROADW,grace:grace,
  onRoad:onRoad(),times:times.slice(),lapT:lapT}}
/* A hit is a cost, not an ending: the pace is cut, a short grace window
   keeps one obstacle from billing twice, and the clock keeps running. */
function hitObstacle(){grace=45;spd=Math.max(PACE*0.35,spd*0.45);
  shake(5);hitstop(3);sfx('clash');burst(car.x,CARY,10,'ALERT_JUICE')}
function crossLine(){times.push(lapT);lapT=0;
  if(lap>=LAPS){state='goal';sfx('win');shake(6);
    burst(car.x,CARY-20,16,'ACCENT_JUICE')}
  else{lap++;sfx('key')}}
const keys={};function K(k){return keys[k]}
addEventListener('keydown',e=>{keys[e.key]=true;
  if(e.key==='ArrowLeft'||e.key==='ArrowRight')e.preventDefault();
  if(e.key==='r'||e.key==='R')reset()});
addEventListener('keyup',e=>{keys[e.key]=false});
function step(){
  if(state==='race'){
    lapT++;
    /* Steering is the one mechanic four templates had each written out
       (C-1114); this is the shared part, with the margin and the speed
       this game chose. */
    partsSteerX(car,3.4,14,W-14);
    /* Off the road the target pace drops and the car eases toward it, and
       recovery is slower than the loss: a mistake reads immediately but is
       paid back over a second, not a frame. */
    const target=onRoad()?PACE:PACE*0.45;
    spd+=(target-spd)*(spd>target?0.08:0.03);
    dist+=spd;
    /* Where we were, at this point on the course. */
    ghostSample(dist,car.x);
    if(grace>0)grace--;
    while(nextObs<dist+CARY+30){
      obs.push({d:nextObs,x:roadAt(nextObs)+(rand()-0.5)*(ROADW-76)});
      nextObs+=GAP+rand()*GAP}
    obs=obs.filter(o=>{
      if(grace===0&&Math.abs(o.d-dist)<14&&Math.abs(o.x-car.x)<26){
        hitObstacle();return false}
      /* Counted as it goes by, so "I got past one" is a thing the page
         knows rather than a thing only the player felt. */
      if(o.d<=dist-14){passed++;return false}
      return o.d>dist-60});
    if(dist>=lap*LAP)crossLine()}
  draw();requestAnimationFrame(step)}
function draw(){
  /* A lap is a scene: the palette steps once per lap and the final lap is
     the brightest frame of the run (§7 観察 5-6). Mood only - the road,
     the obstacles and the off-road state all read by shape and text. */
  setScene(Math.min(lap,LAPS)-1);
  cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(0,0,W,H);
  cx.fillStyle=scenePaint('RAISED_TOKEN');
  for(let y=0;y<H;y+=8){const d=dist+(CARY-y);
    cx.fillRect(roadAt(d)-ROADW/2,y,ROADW,8)}
  /* Edge ticks and the start/finish band are a light neutral, not an
     accent: the boundary is information and has to survive every scene
     palette (§4 - colour is never the only carrier). */
  cx.fillStyle='#dfe7f5';
  for(let y=0;y<H;y+=4){const d=dist+(CARY-y),rx=roadAt(d);
    if(((d%110)+110)%110<12){
      cx.fillRect(rx-ROADW/2,y,5,4);cx.fillRect(rx+ROADW/2-5,y,5,4)}
    if(((d%LAP)+LAP)%LAP<10){
      for(let i=0;i<8;i+=2)cx.fillRect(rx-ROADW/2+i*(ROADW/8),y,ROADW/8,4)}}
  obs.forEach(o=>{const y=CARY-(o.d-dist);if(y<-20||y>H+20)return;
    cx.fillStyle='MAGENTA_TOKEN';cx.fillRect(o.x-11,y-11,22,22);
    cx.strokeStyle='#05070f';cx.lineWidth=3;
    cx.beginPath();cx.moveTo(o.x-6,y-6);cx.lineTo(o.x+6,y+6);
    cx.moveTo(o.x+6,y-6);cx.lineTo(o.x-6,y+6);cx.stroke()});
  /* The past self, behind the car and through it: drawn and nothing
     else - no collision, no score, no sound (C-1401). */
  const gx=ghostAt(dist);
  if(gx!==null){cx.save();cx.globalAlpha=0.32;
    cx.fillStyle=TUNE_ACCENT;cx.fillRect(gx-11,CARY-16,22,32);
    cx.globalAlpha=0.6;cx.strokeStyle=TUNE_ACCENT;cx.lineWidth=1;
    cx.strokeRect(gx-11,CARY-16,22,32);cx.restore()}
  cx.fillStyle='CYAN_TOKEN';cx.fillRect(car.x-11,CARY-16,22,32);
  cx.fillStyle='#05070f';cx.fillRect(car.x-6,CARY-8,12,9);
  if(grace>0){cx.strokeStyle='#dfe7f5';cx.lineWidth=2;
    cx.strokeRect(car.x-13,CARY-18,26,36)}
  cx.fillStyle='#dfe7f5';cx.font='13px ui-monospace,monospace';
  cx.fillText('LAP '+Math.min(lap,LAPS)+'/'+LAPS+'  '+(lapT/60).toFixed(1)+'s',12,19);
  cx.strokeStyle='BORDER_TOKEN';cx.strokeRect(W-172,10,120,10);
  cx.fillStyle='CYAN_TOKEN';cx.fillRect(W-172,10,120*Math.min(1,spd/PACE),10);
  cx.fillStyle='#dfe7f5';
  cx.fillText(onRoad()?'走行':'コース外',W-172,34);
  if(state==='goal'){cx.fillStyle='#05070fd0';cx.fillRect(0,0,W,H);
    cx.fillStyle='#dfe7f5';cx.font='20px ui-monospace,monospace';
    const a='ゴール。';cx.fillText(a,W/2-a.length*10,H/2-52);
    cx.font='13px ui-monospace,monospace';
    let y=H/2-24,total=0;
    times.forEach((f,i)=>{total+=f;
      cx.fillText('LAP '+(i+1)+'  '+(f/60).toFixed(2)+'s',W/2-70,y);y+=18});
    cx.fillText('TOTAL '+(total/60).toFixed(2)+'s',W/2-70,y);
    const b='R でもう一度';cx.fillText(b,W/2-b.length*6.5,y+26)}}
reset();step();
"""

#: The page driven in node: the browser is a no-op proxy, the real script
#: runs, and the race is driven to the finish so the rules can be read back
#: instead of grepped for. Unlike the kaiju probe this one records keyup
#: handlers too - a race is held keys, and a probe that could only press
#: would drive with the wheel stuck.
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
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn(i * 16) } }
function key(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
/* Past the start screen: the gate holds every frame until pressed. */
key('keydown', ' '); key('keyup', ' ');
run(2);
/* Contact first, from a clean start: put an obstacle on the car and read
   what it costs. A race where obstacles cost nothing is scenery. */
const start = raceFacts();
obs.push({ d: start.dist + 4, x: start.carX });
run(6);
const afterHit = raceFacts();
/* Steering, after a reset: hold left, then hold right, and watch the car. */
key('keydown', 'r'); key('keyup', 'r');
run(1);
const centred = raceFacts();
key('keydown', 'ArrowLeft'); run(30); key('keyup', 'ArrowLeft');
const afterLeft = raceFacts();
key('keydown', 'ArrowRight'); run(30); key('keyup', 'ArrowRight');
const afterRight = raceFacts();
/* Now drive it to the finish: steer toward the road's centre each frame and
   let the obstacles that land on the racing line cost what they cost. */
key('keydown', 'r'); key('keyup', 'r');
let frames = 0, lapsSeen = [];
for (let i = 0; i < 9000 && raceFacts().state === 'race'; i++, frames++) {
  const f = raceFacts();
  key('keyup', 'ArrowLeft'); key('keyup', 'ArrowRight');
  if (f.carX < f.road - 6) key('keydown', 'ArrowRight');
  else if (f.carX > f.road + 6) key('keydown', 'ArrowLeft');
  run(1);
  if (raceFacts().lap !== f.lap) lapsSeen.push(i);
}
const end = raceFacts();
const palette = sceneFacts();
console.log(JSON.stringify({
  scenes: palette.scenes,
  stateStart: start.state, base: start.base,
  spdStart: start.spd, spdAfterHit: afterHit.spd, graceAfterHit: afterHit.grace,
  leftMoved: afterLeft.carX - centred.carX,
  rightMoved: afterRight.carX - afterLeft.carX,
  lap: end.lap, laps: end.laps, state: end.state,
  lapTimes: end.times.length, lapCrossings: lapsSeen.length, frames: frames,
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the race can be driven in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = [
    "RACING_DIFFICULTY",
    "RACING_HOW",
    "RACING_SCRIPT",
    "RACING_TITLE",
    "RACING_WORDS",
    "PROBE",
    "probe_source",
]
