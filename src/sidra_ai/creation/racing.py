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

from sidra_ai.creation.probekeys import with_probe_keys

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
#: setting was the one nobody finishes - two laps and a buzzer. Raising the
#: pace to 2.8 would have fixed that by taking away racing's only losing
#: path (every rung then beats the clock), a change to what this template
#: *is*. C-1404 decided (b) instead: the pace ladder stays, and easy runs
#: fewer laps - difficulty scales scope, not only speed, and the clock can
#: still win on every rung when the driving is bad enough.
RACING_DIFFICULTY: dict[str, tuple[float, float]] = {
    "easy": (2.4, 260),
    "normal": (3.0, 190),
    "hard": (3.7, 130),
}

#: Laps per rung (C-1404 決定 (b), corrected by C-1625). Two easy laps take
#: about 45 seconds against the sixty-second clock: finishable, with room
#: left for the mistakes easy exists to forgive - and losable, because a run
#: that keeps hitting obstacles still hears the buzzer.
#:
#: The top rung had the same three laps as normal while running 23% faster,
#: so raising the difficulty made the course SHORTER: hands off the wheel,
#: easy reached the goal at 45.2s, normal at 51.1s and hard at 41.0s - the
#: harshest setting left the most room against the only way this template
#: can be lost (the buzzer before the last line). Four laps puts hard back
#: at the top of its own ladder at 57.3s. Five is over: the same hands-off
#: run hears the buzzer, and C-1404's floor is that the weakest driver still
#: finishes every rung.
RACING_LAPS: dict[str, int] = {
    "easy": 2,
    "normal": 3,
    "hard": 4,
}

RACING_TITLE = "ひかりのサーキット"
RACING_HOW = (
    "← → でハンドルを切る。コース外と障害物は減速（走りは止まらない）。"
    "やさしいは 2 周・ふつうは 3 周・むずかしいは 4 周でゴール、"
    "周回ごとのタイムが残る。R でやり直し、M で消音。"
)

RACING_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const PACE=SPEED_TOKEN,GAP=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const W=cv.width,H=cv.height,CARY=H-56,LAP=1800,LAPS=LAPS_TOKEN,ROADW=190;
/* The course is a function of distance, not a stored array: the same SEED
   bends the same way everywhere, and the probe can ask where the road is.
   The two periods keep the worst drift per frame below the steering speed,
   so the road is always followable at every difficulty. */
const PH1=rand()*6.283,PH2=rand()*6.283;
function roadAt(d){return W/2+Math.sin(d/380+PH1)*150+Math.sin(d/151+PH2)*62}
let car,obs,dist,lap,lapT,times,state,grace,spd,nextObs,passed,slips;
/* The trail (§1, C-1372): ten afterimages of where the car just was,
   fading with age behind it. Speed is what draws the length - the
   samples are one frame apart, so a fast lap stretches them and the
   post-crash crawl shrinks them, §1's weight-proportional rule read
   from the speed side. Decoration: reduced motion never accumulates
   one (C-1020), and a finished run drains a frame at a time. */
let TRAIL=[];
/* The stream the obstacles come out of, back to the top with everything
   else (C-1414). Three other templates already reset their seed here; this
   one did not, so a go that followed a demo - or an R restart - met a
   different set of obstacles on the same course. 「同じ依頼は同じ世界」 is
   the promise SEED makes, and it has to survive a restart. */
function reset(){rs=(SEED>>>0)||1;car={x:roadAt(0),sq:1};obs=[];dist=0;lap=1;lapT=0;times=[];TRAIL=[];
  state='race';grace=0;spd=PACE;nextObs=320;passed=0;slips=0}
setPal(RACING_PAL_TOKEN);
/* HUD contract (§4 WCAG 1.4.3, C-1337): draw() paints through these
   constants, so hudFacts() reports what the frame shows. A lap is a
   scene, so the final lap tints the whole sky and was sinking the themed
   ink to ~3.1:1; the plate is the UNtinted theme surface at 0.7. skies[]
   is the actual per-scene backdrop the plate sits on. */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){const keep=SCENE,sk=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;sk.push(scenePaint('SURFACE_TOKEN'))}
  SCENE=keep;return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A,skies:sk}}
/* The road's edge is information and has to survive every scene of every
   theme (§4, C-1347). One light neutral did not: on the paper theme it
   sat at ~1.05:1 against road AND roadside for the whole run. A TWO-TONE
   mark - dark core, light rim - always has one half standing at 3:1
   against any paint (a mid grey is the worst case, and both halves still
   clear ~4:1 there), and the pair reads against itself. */
const EDGE_A='#05070f',EDGE_B='#dfe7f5';
function edgeFacts(){const keep=SCENE,out=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;
    out.push({surf:scenePaint('SURFACE_TOKEN'),road:scenePaint('RAISED_TOKEN')})}
  SCENE=keep;return {a:EDGE_A,b:EDGE_B,scenes:out}}
/* The far layer (§7 観察 7, C-1400): distance is drawn by CONTRAST, and
   racing was the one template with the distance literally on the screen
   - y=0 is dist+CARY, the course a car-length-and-then-some ahead - and
   nothing at all behind it. C-1036 gave racing 観察 5-6 (a palette per
   lap, the last lap the brightest) and stopped there. Same contract
   shape as the other six: draw() paints through FAR_A, depthFacts()
   reports the per-scene paints, and the judge holds the ridge visible
   against the roadside (>=1.02:1) yet fainter than the border paint it
   is made of.
   The first prescription was to haze the TARMAC toward the horizon, and
   measuring it killed it: the road and the roadside are the same value.
   Driven, all four themes report road-against-roadside at 1.012:1
   (default), 1.067-1.087 (paper/terminal/dusk) - so a road faded into
   the roadside blends to 1.000:1 and there is simply nothing there to
   fade. That is why the boundary has been carried by the two-tone edge
   marks since C-1287 rather than by the tarmac's own colour. Border
   against surface is the pair that does carry value here (1.212-1.650:1
   driven), and at 0.45 - platformer's proven value, C-1354 - the ridge
   measures 1.095-1.292:1 in all twelve theme x lap cells.
   Nothing the player acts on is faded: the edge pair, the start/finish
   band, the obstacles, both ghosts, the trail and the car are all opaque.
   §4's rule is that the boundary is information, so the far layer is new
   scenery behind the course and never a veil over it. */
const FAR_A=0.45,HZ=Math.round(H*0.34),RIDGE_H=34;
function depthFacts(){const keep=SCENE,out=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;
    out.push({sky:scenePaint('SURFACE_TOKEN'),solid:scenePaint('BORDER_TOKEN'),
      alpha:FAR_A})}
  SCENE=keep;return out}
function onRoad(){return Math.abs(car.x-roadAt(dist))<ROADW/2-8}
function raceFacts(){return{state:state,lap:lap,laps:LAPS,dist:dist,spd:spd,sq:car.sq,passed:passed,
  trail:TRAIL.map(s=>s.d),
  slips:slips,
  base:PACE,carX:car.x,road:roadAt(dist),roadW:ROADW,grace:grace,
  onRoad:onRoad(),times:times.slice(),lapT:lapT}}
/* A hit is a cost, not an ending: the pace is cut, a short grace window
   keeps one obstacle from billing twice, and the clock keeps running. */
/* hx is the obstacle's own x (§2 増築, C-1616): burst already knew where
   the hit was, the ear did not. Defaulted to the car so a caller without
   one still gets the old centre-ish sound rather than NaN. */
function hitObstacle(hx){grace=45;spd=Math.max(PACE*0.35,spd*0.45);
  /* Squash & stretch, the crash half (§1, C-1385): the hit crushes the
     body for a beat through C-1332's recipe; under reduced motion the
     silhouette never changes. */
  if(!REDUCED){car.sq=0.7}
  shake(5);hitstop(3);sfx('clash',1,(typeof hx==='number'?hx:car.x)/W);
  burst(car.x,CARY,10,'ALERT_JUICE')}
function crossLine(){times.push(lapT);lapT=0;
  if(lap>=LAPS){state='goal';winBeat(car.x,CARY-20)}
  else{lap++;sfx('key')}}
const keys={};function K(k){return keys[k]}
addEventListener('keydown',e=>{keys[e.key]=true;
  if(e.key==='ArrowLeft'||e.key==='ArrowRight')e.preventDefault();
  if(e.key==='r'||e.key==='R')reset()});
addEventListener('keyup',e=>{keys[e.key]=false});
function step(now){
  /* The world advances on real time, not on this display's refresh rate
     (§26, C-1607). Drawing is NOT gated: on a 120Hz screen the picture
     still lands 120 times a second, the course just stops travelling
     twice as far while it does. */
  if(!TICK(now)){draw();return requestAnimationFrame(step)}
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
    if(!REDUCED){TRAIL.push({x:car.x,d:dist});if(TRAIL.length>10)TRAIL.shift()}
    /* Where we were, at this point on the course. */
    ghostSample(dist,car.x);
    if(grace>0)grace--;
    while(nextObs<dist+CARY+30){
      obs.push({d:nextObs,x:roadAt(nextObs)+(rand()-0.5)*(ROADW-76)});
      nextObs+=GAP+rand()*GAP}
    obs=obs.filter(o=>{
      if(grace===0&&Math.abs(o.d-dist)<14&&Math.abs(o.x-car.x)<26){
        hitObstacle(o.x);return false}
      /* Counted as it goes by, so "I got past one" is a thing the page
         knows rather than a thing only the player felt. */
      if(o.d<=dist-14){passed++;
        /* The slipstream (§13, C-1325): shaving past pays a burst of
           pace. The band starts exactly where the 26px hitbox ends, so
           the reward begins where the risk was real - and a grace-window
           pass-through (inside 26) never pays: an immune crash is not a
           near miss. The existing easing pulls spd back to PACE, so the
           boost is a surge, not a permanent gear. */
        const near=Math.abs(o.x-car.x);
        if(near>=26&&near<46){slips++;
          spd=Math.min(PACE*1.4,spd+PACE*0.3);
          /* The ear and the eye point at the same place (§28, C-1650).
             The pan says which side the near miss happened on - the whole
             point of a slipstream is that it was THAT close on THAT side -
             and the light used to flare over the car, which carries no
             side at all. The firing condition is 26..46px away, so the
             two could never agree by accident. */
          sfx('catch',1,o.x/W);burst(o.x,CARY-8,8,'ACCENT_JUICE')}
        return false}
      return o.d>dist-60});
    if(dist>=lap*LAP)crossLine()}
  /* The engine voice (§25, C-1378): the pace itself, sung every frame -
     PACE*1.4 is the slipstream ceiling, so full boost is the top of the
     octave and the off-road crawl sits near its floor. Gated on the
     round actually playing: the title's attract demo drives this same
     loop (C-1414), and a demo that hums before anyone pressed anything
     would be the engine idling in the shop window. Outside the race the
     engine is off: a result screen does not idle either. */
  let ENG_ON=false;
  try{ENG_ON=state==='race'&&gateState()==='playing'}catch(e){ENG_ON=state==='race'}
  if(ENG_ON){try{engineTick(spd/(PACE*1.4))}catch(e){}}
  else{try{engineStop()}catch(e){}}
  /* The crush settles by quarter-steps and snaps (C-1332), outside the
     race guard so a car on the goal screen still pops back to shape. */
  if(car){car.sq+=(1-car.sq)*0.25;if(Math.abs(car.sq-1)<0.01)car.sq=1}
  if(state!=='race'&&TRAIL.length)TRAIL.shift();
  draw();requestAnimationFrame(step)}
function draw(){
  /* A lap is a scene: the palette steps once per lap and the final lap is
     the brightest frame of the run (§7 観察 5-6). Mood only - the road,
     the obstacles and the off-road state all read by shape and text. */
  /* Three acts however many laps: the last lap is always the brightest
     act, so a two-lap easy run still ends on the climax (§7 観察 6). */
  setScene(LAPS>1?Math.round((Math.min(lap,LAPS)-1)*2/(LAPS-1)):2);
  cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(0,0,W,H);
  /* distance is contrast, not colour (§7 観察 7): a faint ridge along the
     horizon in the theme's own border paint, drawn before the road so the
     course runs in front of its own skyline. FAR_A is the contract
     (C-1400), not decoration. Fixed positions and no scroll of its own:
     what is that far away does not slide, so reduced motion has nothing
     to freeze - catch's cloud reasoning (C-1365), verbatim. */
  cx.globalAlpha=FAR_A;cx.fillStyle=scenePaint('BORDER_TOKEN');
  for(let i=0;i<6;i++){const rx=i*150-45;
    cx.beginPath();cx.moveTo(rx,HZ);cx.lineTo(rx+75,HZ-RIDGE_H);
    cx.lineTo(rx+150,HZ);cx.closePath();cx.fill()}
  cx.globalAlpha=1;
  cx.fillStyle=scenePaint('RAISED_TOKEN');
  for(let y=0;y<H;y+=8){const d=dist+(CARY-y);
    cx.fillRect(roadAt(d)-ROADW/2,y,ROADW,8)}
  /* Edge ticks and the start/finish band are a light neutral, not an
     accent: the boundary is information and has to survive every scene
     palette (§4 - colour is never the only carrier). */
  /* ...and it is information on EVERY row, not one row in four (§4 +
     WCAG 1.4.11, C-1603). The ticks below mark 12 units in every 110, so
     the boundary stood at 3:1 on a quarter of the screen and, everywhere
     else, at whatever the tarmac happened to differ from the roadside by
     - measured at 1.012:1 on the default theme (C-1400). Being on the
     road is not mood: off it the pace halves. So the same two-tone pair
     that the ticks are made of runs the whole length as a thin line, and
     the ticks stay on top of it: the line says where the road is, the
     ticks still say how fast it is going by. */
  for(let y=0;y<H;y+=4){const d=dist+(CARY-y),rx=roadAt(d);
    cx.fillStyle=EDGE_A;
    cx.fillRect(rx-ROADW/2,y,4,4);cx.fillRect(rx+ROADW/2-4,y,4,4);
    cx.fillStyle=EDGE_B;
    cx.fillRect(rx-ROADW/2+1,y,2,4);cx.fillRect(rx+ROADW/2-3,y,2,4);
    if(((d%110)+110)%110<12){
      cx.fillStyle=EDGE_A;
      cx.fillRect(rx-ROADW/2,y,5,4);cx.fillRect(rx+ROADW/2-5,y,5,4);
      cx.fillStyle=EDGE_B;
      cx.fillRect(rx-ROADW/2+1,y+1,3,2);cx.fillRect(rx+ROADW/2-4,y+1,3,2)}
    if(((d%LAP)+LAP)%LAP<10){
      for(let i=0;i<8;i+=2){cx.fillStyle=EDGE_A;
        cx.fillRect(rx-ROADW/2+i*(ROADW/8),y,ROADW/8,4);
        cx.fillStyle=EDGE_B;
        cx.fillRect(rx-ROADW/2+i*(ROADW/8)+1,y+1,ROADW/8-2,2)}}}
  obs.forEach(o=>{const y=CARY-(o.d-dist);if(y<-20||y>H+20)return;
    cx.fillStyle='MAGENTA_TOKEN';cx.fillRect(o.x-11,y-11,22,22);
    cx.strokeStyle='#05070f';cx.lineWidth=3;
    cx.beginPath();cx.moveTo(o.x-6,y-6);cx.lineTo(o.x+6,y+6);
    cx.moveTo(o.x+6,y-6);cx.lineTo(o.x-6,y+6);cx.stroke()});
  /* The second ghost (§11 事実 1, C-1333): the run before this one, an
     outline only and dimmer than the best, drawn first so the record
     sits above it. When the last run IS the record the two coincide and
     honestly read as one. */
  /* The afterimages first, oldest faintest, each where the car held it -
     its past slides down-screen as the course scrolls on. */
  TRAIL.forEach((s,i)=>{const y=CARY+(dist-s.d);if(y>H+20)return;
    const a=(i+1)/TRAIL.length;
    cx.save();cx.globalAlpha=a*0.28;cx.fillStyle='CYAN_TOKEN';
    cx.fillRect(s.x-11,y-16,22,32);cx.restore()});
  const glx=ghostAtLast(dist);
  if(glx!==null){cx.save();cx.globalAlpha=0.35;
    cx.strokeStyle=TUNE_ACCENT;cx.lineWidth=1;
    cx.strokeRect(glx-11,CARY-16,22,32);
    cx.beginPath();cx.moveTo(glx-5,CARY-8);cx.lineTo(glx+5,CARY-8);
    cx.stroke();cx.restore()}
  /* The past self, behind the car and through it: drawn and nothing
     else - no collision, no score, no sound (C-1401). */
  const gx=ghostAt(dist);
  if(gx!==null){cx.save();cx.globalAlpha=0.32;
    cx.fillStyle=TUNE_ACCENT;cx.fillRect(gx-11,CARY-16,22,32);
    cx.globalAlpha=0.6;cx.strokeStyle=TUNE_ACCENT;cx.lineWidth=1;
    cx.strokeRect(gx-11,CARY-16,22,32);cx.restore()}
  /* One bottom-anchored transform for body and windshield together, so
     the crush reads as the car deforming, not parts sliding (C-1385).
     At sq=1 every coordinate is bit-identical to the old literals. */
  const csq=car.sq,csw=2-csq;
  cx.fillStyle='CYAN_TOKEN';
  cx.fillRect(car.x-11*csw,CARY+16-32*csq,22*csw,32*csq);
  cx.fillStyle='#05070f';
  cx.fillRect(car.x-6*csw,CARY+16-24*csq,12*csw,9*csq);
  if(grace>0){cx.strokeStyle=EDGE_A;cx.lineWidth=4;
    cx.strokeRect(car.x-13,CARY-18,26,36);
    cx.strokeStyle=EDGE_B;cx.lineWidth=2;
    cx.strokeRect(car.x-13,CARY-18,26,36);cx.lineWidth=1}
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(6,4,262,22);cx.fillRect(W-178,4,132,38);cx.globalAlpha=1;
  cx.fillStyle=HUD_INK;cx.font='13px ui-monospace,monospace';
  cx.fillText('LAP '+Math.min(lap,LAPS)+'/'+LAPS+'  '+(lapT/60).toFixed(1)+'s'+
    (slips>0?'  ニアミス '+slips:''),12,19);
  cx.strokeStyle='BORDER_TOKEN';cx.strokeRect(W-172,10,120,10);
  cx.fillStyle='CYAN_TOKEN';cx.fillRect(W-172,10,120*Math.min(1,spd/PACE),10);
  cx.fillStyle=HUD_INK;
  cx.fillText(onRoad()?'走行':'コース外',W-172,34);
  if(state==='goal'){cx.fillStyle='SCRIM_TOKEN'+'d0';cx.fillRect(0,0,W,H);
    cx.fillStyle='INK_TOKEN';cx.font='20px ui-monospace,monospace';
    const a='ゴール。';cx.fillText(a,W/2-a.length*10,H/2-52);
    cx.font='13px ui-monospace,monospace';
    let y=H/2-24,total=0;
    times.forEach((f,i)=>{total+=f;
      cx.fillText('LAP '+(i+1)+'  '+(f/60).toFixed(2)+'s',W/2-70,y);y+=18});
    cx.fillText('TOTAL '+(total/60).toFixed(2)+'s',W/2-70,y);
    if((typeof roundAskReady!=='function'||roundAskReady())){const b='R でもう一度';cx.fillText(b,W/2-b.length*6.5,y+26)}}}
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
/* Which scene the page was actually IN, in the order it went (C-1640).
   sceneFacts().scenes is the palette table - three colours that exist -
   and the contract read only that, so a page that painted act 0 for the
   whole race passed. This is the other half: the acts, as they happened. */
const sceneOrder = [];
for (let i = 0; i < 9000 && raceFacts().state === 'race'; i++, frames++) {
  const f = raceFacts();
  key('keyup', 'ArrowLeft'); key('keyup', 'ArrowRight');
  if (f.carX < f.road - 6) key('keydown', 'ArrowRight');
  else if (f.carX > f.road + 6) key('keydown', 'ArrowLeft');
  run(1);
  const at = sceneFacts().scene;
  if (sceneOrder[sceneOrder.length - 1] !== at) sceneOrder.push(at);
  if (raceFacts().lap !== f.lap) lapsSeen.push(i);
}
const end = raceFacts();
const palette = sceneFacts();
console.log(JSON.stringify({
  scenes: palette.scenes, sceneOrder: sceneOrder,
  hud: hudFacts(),
  edge: edgeFacts(),
  depth: depthFacts(),
  stateStart: start.state, base: start.base,
  spdStart: start.spd, spdAfterHit: afterHit.spd, graceAfterHit: afterHit.grace,
  leftMoved: afterLeft.carX - centred.carX,
  rightMoved: afterRight.carX - afterLeft.carX,
  lap: end.lap, laps: end.laps, state: end.state,
  lapTimes: end.times.length, lapCrossings: lapsSeen.length, frames: frames,
}));
"""


#: The slipstream, shaved for real (§13, C-1325): one obstacle pinned just
#: outside the hitbox pays a surge that decays; one far off pays nothing;
#: one dead centre still cuts the pace and pays nothing.
SLIP_PROBE = """
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
(handlers.keydown || []).forEach(fn => fn({ key: ' ', code: 'Space',
  preventDefault(){}, stopImmediatePropagation(){} }));
run(5);
/* The course is emptied and natural spawns stopped, so each scenario is
   exactly one obstacle. The car is held on the road's centre line and
   the obstacle rides at a fixed lateral offset until it passes, so the
   geometry at the pass is the offset itself, not luck. */
obs.length = 0; nextObs = 1e9;
function passOne(offset, gap){
  const before = { slips: raceFacts().slips, passed: raceFacts().passed };
  const o = { d: raceFacts().dist + (gap || 120), x: 0 };
  obs.push(o);
  let maxSpd = 0, minSpd = 99;
  for (let i = 0; i < 300 && raceFacts().passed === before.passed
       && obs.indexOf(o) >= 0; i++) {
    car.x = raceFacts().road;
    o.x = car.x + offset;
    run(1);
    const v = raceFacts().spd;
    if (v > maxSpd) maxSpd = v;
    if (v < minSpd) minSpd = v;
  }
  run(2);
  return { slips: raceFacts().slips - before.slips,
    maxSpd: maxSpd, minSpd: minSpd };
}
const near = passOne(34);
/* The surge is a surge: the easing brings the pace back down. */
for (let i = 0; i < 150; i++) { car.x = raceFacts().road; run(1) }
const settledSpd = raceFacts().spd;
const far = passOne(80);
const hit = passOne(0);
/* A second centred obstacle ridden through immediately, inside the grace
   window: an immune crash is not a near miss and must pay nothing. */
const graced = passOne(0, 26);
console.log(JSON.stringify({ near: near, settledSpd: settledSpd,
  far: far, hit: hit, graced: graced, graceLeft: raceFacts().grace,
  base: raceFacts().base, state: raceFacts().state }));
"""


def slip_probe(script: str) -> str:
    """The page's own script, wrapped so a near miss can be shaved."""

    return SLIP_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The trail, as raced (§1, C-1372). The page is really driven: at pace
#: the ten afterimages fill and stretch, off the road the crawl shrinks
#: their span, the finish drains them a frame at a time, and reduced
#: motion never accumulates one.
TRAIL_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => rec }) };
/* A recording context, because the numbers above are bookkeeping and
   bookkeeping is not paint (C-1615, C-1618, C-1628 - three times, and the
   first two bodies of this very metric were still reading only the facts).
   globalAlpha is tracked across save/restore so an afterimage cannot be
   counted at the body's own opacity. */
let ALPHA = 1, OPS = [];
const STACK = [];
const rec = new Proxy(function(){}, {
  get: (t, k) => {
    if (k === 'globalAlpha') return ALPHA;
    if (k === 'save') return () => { STACK.push(ALPHA) };
    if (k === 'restore') return () => { ALPHA = STACK.length ? STACK.pop() : 1 };
    if (k === 'fillRect') return (x, y, w, h) => { OPS.push({ op: 'rect', w: w, h: h, a: ALPHA }) };
    if (k === 'arc') return (x, y, r) => { OPS.push({ op: 'arc', r: r, a: ALPHA }) };
    if (k === Symbol.toPrimitive) return () => 0;
    return nothing },
  set: (t, k, v) => { if (k === 'globalAlpha') { ALPHA = v } return true },
  apply: () => nothing });
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
key(' ');
run(80);
const fast = raceFacts();
/* One frame, recorded. The afterimages are the car's own 22x32 body
   drawn at a*0.28, so the shape and the ceiling together name them. */
OPS = [];
run(1);
const faint = OPS.filter(o => o.op === 'rect'
  && Math.abs(o.w - 22) < 1e-9 && Math.abs(o.h - 32) < 1e-9
  && o.a > 0 && o.a <= 0.2801);
const painted = faint.length;
const paintedMax = painted ? Math.max.apply(null, faint.map(o => o.a)) : 0;
const bodyDrawn = OPS.some(o => o.op === 'rect'
  && Math.abs(o.w - 22) < 1e-9 && Math.abs(o.h - 32) < 1e-9 && o.a > 0.999);
const fastBehind = fast.trail.every(d => d <= fast.dist);
const fastSpan = fast.trail.length ? fast.dist - Math.min.apply(null, fast.trail) : 0;
/* Park the car off the road: the crawl must shrink the streak. */
car.x = 2;
run(160);
const slow = raceFacts();
const slowSpan = slow.trail.length ? slow.dist - Math.min.apply(null, slow.trail) : 0;
/* End the run the page's own way and watch the streak drain. */
state = 'goal';
let drained = null;
for (let i = 0; i < 20 && drained === null; i++) { run(1);
  if (raceFacts().trail.length === 0) drained = i }
console.log(JSON.stringify({ painted: painted, paintedMax: paintedMax,
  bodyDrawn: bodyDrawn,
  full: fast.trail.length, behind: fastBehind,
  fastSpan: fastSpan, slowSpan: slowSpan, spdFast: fast.spd, spdSlow: slow.spd,
  drained: drained }));
"""


#: The crash, crushed and settled (§1, C-1385): a real obstacle strike
#: must crush the body to 0.7 and walk it back to exactly 1 within thirty
#: frames; under reduced motion the same strike cuts the pace but never
#: bends the silhouette.
SQUASH_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => rec }) };
/* A recording context, because `sq` is a number and squash & stretch is
   a shape (C-1636). adventure and shooter already read their own paint;
   this is the same reading for the rest. */
let RECTS = [];
const rec = new Proxy(function(){}, {
  get: (t, k) => {
    if (k === 'fillRect') return (x, y, w, h) => { RECTS.push({ w: w, h: h }) };
    if (k === Symbol.toPrimitive) return () => 0;
    return nothing },
  set: () => true, apply: () => nothing });
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { RECTS = []; const fn = queued; queued = null; fn((F++) * 16) } }
/* Did the paint follow the number? The rest frame's fills are kept and
   a squashed frame has to contain one of them under the template's own
   one-body transform - width the other way, height with it. Nothing is
   hardcoded: the dimensions come from the page's own rest frame. */
let restFills = [];
function followed(sq){
  if (Math.abs(sq - 1) < 1e-9) return false;
  return restFills.some(r => RECTS.some(n =>
    Math.abs(n.w - r.w * (2 - sq)) < 1e-6 && Math.abs(n.h - r.h * sq) < 1e-6)) }

function key(k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' ');
/* On the road, at pace, body at rest. */
for (let i = 0; i < 30; i++) { car.x = roadAt(dist); run(1) }
const idle = raceFacts().sq;
restFills = RECTS.slice();
let hitDrawn = 0, idleDrawn = 0;
for (let i = 0; i < 10; i++) { run(1); if (followed(0.7)) idleDrawn++ }
const spdBefore = raceFacts().spd;
/* A certain crash: an obstacle placed on the car, grace open. */
grace = 0;
obs.push({ d: dist + 10, x: car.x });
let hit = null, guard = 0;
while (hit === null && guard++ < 30) { car.x = roadAt(dist); run(1);
  if (raceFacts().spd < spdBefore * 0.7) { hit = raceFacts().sq } }
if (hit !== null && hit < 0.95 && followed(hit)) hitDrawn++;
const trace = [];
for (let i = 0; i < 30; i++) { run(1); trace.push(raceFacts().sq);
  if (raceFacts().sq < 0.95 && followed(raceFacts().sq)) hitDrawn++ }
console.log(JSON.stringify({ hitDrawn: hitDrawn, idleDrawn: idleDrawn,
  restFills: restFills.length, idle: idle, hit: hit, trace: trace,
  settled: raceFacts().sq, spdCut: raceFacts().spd < spdBefore }));
"""


def squash_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the crash's crush can be watched."""

    return SQUASH_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The engine, heard (§25, C-1378): a fake AudioContext records the one
#: oscillator the voice builds, the probe drives a fast stretch and an
#: off-road crawl, and the pitch and gain must follow the pace - higher
#: and fuller at speed, lower and softer in the crawl. The goal screen
#: stops the engine, and M mutes it within a frame.
ENGINE_PROBE = """
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
const OSCS = [];
function FakeOsc(){ this.type = ''; this.frequency = { value: 0 };
  this.started = false; this.stopped = false }
FakeOsc.prototype.start = function(){ this.started = true };
FakeOsc.prototype.stop = function(){ this.stopped = true };
FakeOsc.prototype.connect = function(){};
FakeOsc.prototype.disconnect = function(){};
function FakeCtx(){ this.currentTime = 0; this.state = 'running';
  this.destination = {} }
FakeCtx.prototype.createOscillator = function(){ const o = new FakeOsc();
  OSCS.push(o); return o };
FakeCtx.prototype.createGain = function(){ return { gain: { value: 0,
    setValueAtTime(){}, exponentialRampToValueAtTime(){}, linearRampToValueAtTime(){} },
  connect(){}, disconnect(){} } };
FakeCtx.prototype.createBiquadFilter = function(){ return { type: '',
  frequency: { value: 0 }, connect(){}, disconnect(){} } };
FakeCtx.prototype.createBuffer = function(){ return { getChannelData: () => new Float32Array(8) } };
FakeCtx.prototype.createBufferSource = function(){ return { buffer: null,
  loop: false, connect(){}, start(){}, stop(){} } };
FakeCtx.prototype.resume = function(){};
globalThis.window = globalThis;
globalThis.AudioContext = FakeCtx;
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
const before = engineFacts().on;
key(' ');
/* A clean fast stretch: held to the road's centre every frame, so the
   pace eases up to PACE and the voice sits high in its octave. */
for (let i = 0; i < 80; i++) { car.x = roadAt(dist); run(1) }
const fast = { facts: engineFacts(), spd: raceFacts().spd };
/* Off the road: the pace decays and the voice must sink with it. */
for (let i = 0; i < 160; i++) { car.x = 2; run(1) }
const crawl = { facts: engineFacts(), spd: raceFacts().spd };
car.x = roadAt(dist);
run(40);
/* The goal screen does not idle. */
state = 'goal';
run(3);
const atGoal = engineFacts().on;
/* Back on the road, then M - the mute must land within a frame. */
state = 'race';
run(10);
const beforeMute = engineFacts().on;
key('m');
run(2);
const afterMute = engineFacts().on;
console.log(JSON.stringify({
  before: before, fast: fast, crawl: crawl, atGoal: atGoal,
  beforeMute: beforeMute, afterMute: afterMute,
  oscTypes: OSCS.map(o => o.type),
}));
"""


def engine_probe(script: str) -> str:
    """The page's own script, wrapped so the engine can be heard."""

    return ENGINE_PROBE.replace("SCRIPT_PLACEHOLDER", script)


def trail_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the streak can be watched."""

    return TRAIL_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The far layer, as painted (§7 観察 7, C-1400). A recording context that
#: tracks ``globalAlpha`` across ``save``/``restore`` and keeps every
#: ``fillRect`` and path ``fill`` of one real frame, in order, so the
#: ridge is read off the paints rather than off the constant - and so the
#: things a driver acts on can be shown to be opaque.
HAZE_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
let PAINTS = [], PTS = [];
const CTX = { globalAlpha: 1, fillStyle: '', strokeStyle: '', lineWidth: 1,
  font: '', textAlign: '', globalCompositeOperation: '', lineJoin: '',
  lineCap: '', shadowBlur: 0, shadowColor: '' };
const STACK = [];
const rec = new Proxy(CTX, {
  get(t, k){
    if (k in t && typeof t[k] !== 'function') return t[k];
    if (k === 'save') return () => { STACK.push(Object.assign({}, CTX)) };
    if (k === 'restore') return () => { Object.assign(CTX, STACK.pop() || {}) };
    if (k === 'fillRect') return (x, y, w, h) => {
      PAINTS.push({ kind: 'rect', style: String(CTX.fillStyle),
        alpha: CTX.globalAlpha, x: x, y: y, w: w, h: h }) };
    if (k === 'beginPath') return () => { PTS = [] };
    if (k === 'moveTo' || k === 'lineTo') return (x, y) => { PTS.push([x, y]) };
    if (k === 'fill') return () => {
      if (!PTS.length) return;
      PAINTS.push({ kind: 'fill', style: String(CTX.fillStyle),
        alpha: CTX.globalAlpha,
        y0: Math.min.apply(null, PTS.map(p => p[1])),
        y1: Math.max.apply(null, PTS.map(p => p[1])) }) };
    if (k === 'createLinearGradient' || k === 'createRadialGradient')
      return () => ({ addColorStop(){} });
    if (k === 'measureText') return () => ({ width: 10 });
    return () => undefined },
  set(t, k, v){ t[k] = v; return true } });
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => rec }) };
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
key(' ');
run(40);
/* Put an obstacle in the haze band and one under the wheels, so the
   frame we read carries both - a hazard must never be hazed. */
const now = raceFacts();
obs.push({ d: now.dist + (H - 8), x: now.road });
obs.push({ d: now.dist + 20, x: now.road });
PAINTS = [];
run(1);
/* The tarmac rows are the only ROADW x 8 fills in the frame - the edge
   pair is 5x4/3x2, the finish band ROADW/8 wide, an obstacle 22x22, an
   afterimage 22x32 - so they are picked out by shape, not by re-deriving
   a palette through a token name this wrapper cannot substitute. The
   ridge is named by the contract itself: depthFacts() reports the border
   paint of the lap being drawn. */
const rowIdx = PAINTS.map((p, i) => [p, i])
  .filter(([p]) => p.kind === 'rect' && p.w === ROADW && p.h === 8);
const rows = rowIdx.map(([p]) => p).sort((a, b) => a.y - b.y);
const solid = depthFacts()[SCENE].solid;
const ridgeIdx = PAINTS.map((p, i) => [p, i])
  .filter(([p]) => p.kind === 'fill' && p.style === solid);
const ridge = ridgeIdx.map(([p]) => p);
const others = PAINTS.filter(p => p.kind === 'rect' && !(p.w === ROADW && p.h === 8));
const edges = others.filter(p => p.style === EDGE_A || p.style === EDGE_B);
console.log(JSON.stringify({
  H: H, hz: HZ, far: FAR_A, ridgeH: RIDGE_H, scene: SCENE,
  rowStyles: Array.from(new Set(rows.map(p => p.style))),
  rowAlphas: Array.from(new Set(rows.map(p => p.alpha))).sort(),
  rowCount: rows.length,
  contract: depthFacts().length,
  ridgeCount: ridge.length,
  ridgeAlphas: Array.from(new Set(ridge.map(p => p.alpha))).sort(),
  ridgeLow: ridge.length ? Math.max.apply(null, ridge.map(p => p.y1)) : null,
  ridgeTop: ridge.length ? Math.min.apply(null, ridge.map(p => p.y0)) : null,
  /* The course runs in front of its own skyline: every ridge fill is laid
     down before the first tarmac row. */
  ridgeLast: ridgeIdx.length ? Math.max.apply(null, ridgeIdx.map(e => e[1])) : null,
  roadFirst: rowIdx.length ? Math.min.apply(null, rowIdx.map(e => e[1])) : null,
  edgeCount: edges.length,
  edgeAlphas: Array.from(new Set(edges.map(p => p.alpha))).sort(),
  /* Coverage (§4 + WCAG 1.4.11, C-1603): how many of the frame's row
     slots carry a boundary mark on BOTH sides of the road. Before the
     continuous line this was 19 of 80 - the ticks' 12-in-110 window -
     and everywhere else the boundary was carried by the tarmac's own
     1.012:1 against the roadside. */
  rowSlots: Math.ceil(H / 4),
  boundedRows: (function(){
    const byY = {};
    edges.filter(p => p.y % 4 === 0).forEach(p => {
      (byY[p.y] = byY[p.y] || []).push(p.x) });
    return Object.keys(byY).filter(y => {
      const xs = byY[y];
      return Math.max.apply(null, xs) - Math.min.apply(null, xs) > ROADW / 2;
    }).length })(),
  /* The ticks' own rhythm must survive underneath the line. */
  dashRows: Array.from(new Set(edges.filter(p => p.w === 5).map(p => p.y))).length,
  obsAlphas: Array.from(new Set(others
    .filter(p => p.w === 22 && p.h === 22).map(p => p.alpha))).sort(),
  obsYs: others.filter(p => p.w === 22 && p.h === 22).map(p => p.y).sort((a,b)=>a-b)
}));
"""


#: The world's speed against the display's speed (§26, C-1607). Drives a
#: real race with rAF turned at a chosen refresh rate and reports how far
#: the course travelled in three REAL seconds, so "is this game the same
#: game on a 120Hz phone" is a measurement rather than an argument. A
#: second of warm-up first: the round gate and the accumulator both have
#: first frames, and they are not what this is asking about.
RATE_PROBE = """
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
  getContext: () => paintCounter }) };
/* Counts paints so the claim "drawing is NOT gated" can be measured: on
   a 120Hz screen the picture must still land 120 times a second even
   though the world only advances 60. */
let PAINTS = 0;
const paintCounter = new Proxy({}, {
  get(t, k){
    if (k === 'fillRect') return () => { PAINTS++ };
    if (k === 'createLinearGradient' || k === 'createRadialGradient')
      return () => ({ addColorStop(){} });
    if (k === 'measureText') return () => ({ width: 10 });
    if (k in t) return t[k];
    return () => undefined },
  set(t, k, v){ t[k] = v; return true } });
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
const RATE = RATE_INPUT, STEP = 1000 / RATE, STALL = STALL_INPUT;
let MS = 0, FRAMES = 0, ADVANCED = 0;
/* A frame that moved the course is a frame the world stepped on. Counted
   from the outside, so nothing in the page has to know it is measured. */
function run(n){ for (let i = 0; i < n && queued; i++) {
  const fn = queued; queued = null; MS += STEP; FRAMES++;
  const before = raceFacts().dist; fn(MS);
  if (raceFacts().dist !== before) { ADVANCED++ } } }
function key(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
key('keydown', ' '); key('keyup', ' ');
run(Math.round(RATE));
/* Optionally hand the page one enormous gap - a backgrounded tab - and
   see whether it banks the debt and spends it afterwards (§26 事実 4). */
if (STALL > 0 && queued) { const fn = queued; queued = null; MS += STALL; fn(MS) }
const d0 = raceFacts().dist, f0 = FRAMES, m0 = MS, p0 = PAINTS, a0 = ADVANCED;
run(Math.round(RATE * 3));
console.log(JSON.stringify({
  hz: RATE,
  dist: Math.round((raceFacts().dist - d0) * 100) / 100,
  realMs: Math.round(MS - m0),
  frames: FRAMES - f0,
  advanced: ADVANCED - a0,
  paints: PAINTS - p0,
  clockMs: Math.round(roundFacts().ms)
}));
"""


def rate_probe(script: str, *, hz: float, stall_ms: float = 0.0) -> str:
    """Drive the race with rAF firing at ``hz`` and report real-time speed.

    ``stall_ms`` hands the page one huge gap between callbacks first - a
    backgrounded tab - so the accumulator can be shown not to bank the
    debt and spend it once the tab comes back.
    """

    return (
        RATE_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("RATE_INPUT", repr(float(hz)))
        .replace("STALL_INPUT", repr(float(stall_ms)))
    )


def haze_probe(script: str) -> str:
    """Drive a real race one frame and report what the road was painted at."""

    return HAZE_PROBE.replace("SCRIPT_PLACEHOLDER", script)



#: The ear and the eye, watched in the same frame (§28, C-1650). GAG's
#: intermediate hearing guideline asks that supplementary information
#: carried by audio - it names the direction you are being shot from -
#: be replicated in visuals. C-1394 gave SIDRA a pan channel; this reads
#: whether the light lands where the pan says it happened. Both are the
#: page's own runtime calls, driven for real, not literals off the source.
EAR_EYE_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
const pans = [];
function Recorder(){ this.currentTime = 0; this.state = 'running';
  this.destination = { kind: 'dest' }; this.sampleRate = 44100;
  this.resume = function(){} }
Recorder.prototype.createGain = function(){ return {
  gain: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
  connect(){} } };
Recorder.prototype.createOscillator = function(){ return { type: '',
  frequency: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
  setPeriodicWave(){}, connect(){}, start(){}, stop(){} } };
Recorder.prototype.createPeriodicWave = function(){ return {} };
Recorder.prototype.createBuffer = function(ch, len){ return {
  getChannelData: () => new Float32Array(len) } };
Recorder.prototype.createBufferSource = function(){ return { buffer: null,
  connect(){}, start(){}, stop(){} } };
Recorder.prototype.createBiquadFilter = function(){ return { type: '',
  frequency: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
  connect(){} } };
Recorder.prototype.createStereoPanner = function(){ return {
  pan: { setValueAtTime(v){ pans.push(v) } }, connect(){} } };
globalThis.window = { AudioContext: Recorder };
globalThis.matchMedia = () => ({ matches: false });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
PROBE_KEYS_PLACEHOLDER
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function key(type, k){
  const e = probeKey(k);
  (handlers[type] || []).forEach(fn => fn(e));
}
/* Watch the page's own two channels. Wrapping them reads what the page
   did at run time - the same evidentiary level the pan contract already
   uses - not a literal read out of the source. */
const heard = [];
const seen = [];
const realSfx = sfx, realBurst = burst;
sfx = function(name, pitch, at){
  const was = pans.length;
  const out = realSfx.apply(this, arguments);
  heard.push({ name: String(name), at: (typeof at === 'number' ? at : null),
    pan: pans.length > was ? pans[pans.length - 1] : null, frame: F });
  return out };
burst = function(x, y, n, colour){
  seen.push({ x: x, colour: String(colour), frame: F });
  return realBurst.apply(this, arguments) };

key('keydown', 'r'); key('keyup', 'r'); run(2);
/* Drive a slipstream: put one obstacle exactly in the reward band - past
   the 26px hitbox, inside 46 - and let the page carry it by. The page's
   own filter decides whether it counts; nothing here scores it. */
const eeW = cv.width;
let slip = null;
for (let attempt = 0; attempt < 60 && slip === null; attempt++) {
  const f = raceFacts();
  obs.length = 0;
  const side = attempt % 2 === 0 ? 1 : -1;
  obs.push({ d: f.dist + 16, x: f.carX + side * 34 });
  const slipsBefore = f.slips;
  const hEnd = heard.length, sEnd = seen.length;
  for (let i = 0; i < 40 && slip === null; i++) {
    run(1);
    if (raceFacts().slips > slipsBefore) {
      slip = { side: side,
        heard: heard.slice(hEnd).filter(h => h.name === 'catch'),
        /* Every burst in the window. The colour name is a build-time
           token replaced with a real hex before the page ever runs, so
           filtering on it matches nothing. */
        seen: seen.slice(sEnd),
        carX: f.carX, obsX: f.carX + side * 34 };
    }
  }
}
console.log(JSON.stringify({ slip: slip, width: eeW }));
"""


def ear_eye_probe(script: str) -> str:
    """The page's own script, wrapped so ear and eye can be compared."""

    return with_probe_keys(EAR_EYE_PROBE.replace("SCRIPT_PLACEHOLDER", script))


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the race can be driven in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The obstacle's place, as heard (§2 増築, C-1616). Two obstacles are
#: clipped - one left of the racing line, one right - and one is passed at
#: slipstream range, with the panner values read off the real audio graph.
PAN_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
const pans = [];
function Recorder(){ this.currentTime = 0; this.state = 'running';
  this.destination = { kind: 'dest' }; this.sampleRate = 44100;
  this.resume = function(){} }
Recorder.prototype.createGain = function(){ return {
  gain: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
  connect(){} } };
Recorder.prototype.createOscillator = function(){ return { type: '',
  frequency: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
  setPeriodicWave(){}, connect(){}, start(){}, stop(){} } };
Recorder.prototype.createPeriodicWave = function(){ return {} };
Recorder.prototype.createBuffer = function(ch, len){ return {
  getChannelData: () => new Float32Array(len) } };
Recorder.prototype.createBufferSource = function(){ return { buffer: null,
  connect(){}, start(){}, stop(){} } };
Recorder.prototype.createBiquadFilter = function(){ return { type: '',
  frequency: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
  connect(){} } };
Recorder.prototype.createStereoPanner = function(){ return {
  pan: { setValueAtTime(v){ pans.push(v) } }, connect(){} } };
globalThis.window = { AudioContext: Recorder };
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
function ev(type, k){
  let stopped = false;
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){ stopped = true } };
  for (const fn of (handlers[type] || [])) { fn(e); if (stopped) break }
}
ev('keydown', ' '); ev('keyup', ' ');
run(3);
/* The engine note and the start are positionless. */
const before = pans.length;
/* Clip one obstacle on the left of the road and one on the right: the
   crash is what the ear should place. */
function clip(side){
  /* Run until the crash registers rather than a fixed count: the previous
     crash's hitstop(3) swallows whole callbacks, and two frames of a
     frozen world hit nothing. */
  const f = raceFacts();
  const want = pans.length + 1;
  /* The obstacle sits 20px off the racing line - inside the 26px hitbox,
     so it still lands, and NOT on top of the car. Parking the car on the
     obstacle would make car.x and o.x the same number, and the check
     could not tell "where the hit was" from "where I was". */
  const x = f.road + side * 20;
  obs.length = 0; grace = 0; car.x = f.road;
  obs.push({ d: f.dist + 4, x: x });
  for (let i = 0; i < 30 && pans.length < want; i++) {
    grace = 0; car.x = f.road;
    run(1);
  }
  return x;
}
const leftX = clip(-1);
const rightX = clip(1);
const crashes = pans.length - before;
/* Now a clean pass at slipstream range - close, but not a hit. */
/* A clean pass at slipstream range: close enough to pay, far enough not
   to hit. The obstacle has to get 14 units BEHIND the car to count, which
   at the post-crash crawl takes a while - so drive until it is counted. */
const g = raceFacts();
obs.length = 0; grace = 45; car.x = g.road;
const slipX = g.road + 34;
obs.push({ d: g.dist + 30, x: slipX });
for (let i = 0; i < 300 && !raceFacts().slips; i++) {
  car.x = g.road;
  run(1);
}
console.log(JSON.stringify({ before: before, pans: pans, crashes: crashes,
  expected: [(leftX / W * 2 - 1) * 0.8, (rightX / W * 2 - 1) * 0.8,
             (slipX / W * 2 - 1) * 0.8],
  slips: raceFacts().slips }));
"""


def pan_probe(script: str) -> str:
    """The page's own script, wrapped so a crash's stereo place can be read."""

    return PAN_PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = [
    "PAN_PROBE",
    "pan_probe",
    "SQUASH_PROBE",
    "squash_probe",
    "ENGINE_PROBE",
    "engine_probe",
    "TRAIL_PROBE",
    "trail_probe",
    "HAZE_PROBE",
    "haze_probe",
    "RATE_PROBE",
    "rate_probe",
    "RACING_DIFFICULTY",
    "RACING_HOW",
    "RACING_SCRIPT",
    "RACING_TITLE",
    "RACING_WORDS",
    "PROBE",
    "SLIP_PROBE",
    "slip_probe",
    "probe_source",
]
