"""The vertical shooter - the genre C-1012 had to apologise for by name.

Until now "シューティングゲームを作って" got a fishing game and an honest
sentence saying so. The sentence was the right behaviour and a poor
consolation; this is the template that makes it unnecessary. The honesty
machinery needs no edit when it lands - ``games._GENRES`` already promises
``shooter``, and a genre counts as supported when its key is in
``TEMPLATES``, so the apology retires itself.

What the genre actually is, kept to the parts that carry it: a ship you
steer, a stream you fire, waves that come down in formation and get faster,
and a life count that makes a near miss mean something. The waves are seeded
from the request, so the same words are the same fight - the property the
duel template established and the reason "難しくして" is a different game
rather than different wording.

Token contract, shared with every template: ``SPEED_TOKEN`` is how fast the
waves descend, ``BAND_TOKEN`` the frames between spawns, ``SEED_TOKEN`` the
formation seed. ``REDUCED``/``FRAME`` come from the animation preamble - the
starfield and the thruster flicker freeze under reduced motion while the
shooting keeps working - and ``sfx``/``shake``/``hitstop``/``burst`` come
from the audio and juice preambles. ``setPal``/``setScene``/``scenePaint``
come from the scene preamble: the 60-second round is three acts, the sky
steps once per act, and the final act is the brightest frame of the fight
(§7 観察 5-6), so 第 N 波 is something the picture says too.
"""

from __future__ import annotations

#: Words that pick this template.
SHOOTER_WORDS: tuple[str, ...] = (
    "シューティング",
    "シューター",
    "弾幕",
    "宇宙船",
    "自機",
    "インベーダー",
    "shooting",
    "shooter",
    "shmup",
    "stg",
)

#: (descent speed, frames between waves).
SHOOTER_DIFFICULTY: dict[str, tuple[float, float]] = {
    "easy": (0.5, 110),
    "normal": (0.8, 80),
    "hard": (1.25, 52),
}

SHOOTER_TITLE = "たてスクロール迎撃"
SHOOTER_HOW = (
    "← → で移動、SPACE で連射。敵の波を落とす。連続で落とすほど倍率が上がり、"
    "ぶつかると 1 倍に戻る。3 回ぶつかると終わり。R でやり直し、M で消音。"
)

SHOOTER_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const FALL=SPEED_TOKEN,WAVE=BAND_TOKEN,SEED=SEED_TOKEN;
setPal(SHOOTER_PAL_TOKEN);
/* HUD contract (§4 WCAG 1.4.3, C-1334): draw() paints the HUD through
   these constants and hudFacts() reports them, so the metric can blend
   the plate over every measured sky the way the canvas does. The plate
   is the untinted theme surface at 0.7: the brightest final act was
   sinking the themed ink to ~3:1 here too (C-1329's fix, template 4). */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A}}
/* The hit's other half, as a fact (§1, C-1361). */
function kbFacts(){return {kvx:ship.kvx,x:ship.x,hp:ship.hp,rk:ship.rk,sq:ship.sq}}
/* The far layer (§7 観察 7, C-1360): the starfield's parallax already had
   a speed gradient and no contrast gradient - every star was the same
   hardcoded #ffffff44, so a fast star and a slow one read as the same
   distance, and the literal white sank into the light themes' skies.
   Distance is drawn by CONTRAST: the slow stars (s<NEAR) are the far
   layer, the theme's own border paint faded by FAR_A toward the sky; the
   fast stars are the midground at full strength; the ship and the hulls
   keep their information colours in front. Speed and faintness now point
   the same way. Same contract shape as kaiju's, duel's and platformer's:
   draw() paints through FAR_A and depthFacts() reports the per-scene
   paints for the judge to blend. */
const FAR_A=0.45,NEAR=1.1;
function depthFacts(){const keep=SCENE,out=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;
    out.push({sky:scenePaint('SURFACE_TOKEN'),solid:scenePaint('BORDER_TOKEN'),
      alpha:FAR_A})}
  SCENE=keep;return out}
/* The 60-second round in three acts (game-design-notes.md §7 観察 5-6):
   the HUD already counts 第 N 波, so the sky agrees with it. ACT is a
   third of the round in frames; the final third is the brightest sky of
   the fight, because the wave the clock catches you on is the climax. */
const ACT=1200;
/* §6 観察 3: escalation has a shape - the same fight, re-accelerated. Each
   act drops faster and spawns denser than the last, so the sky's colour
   change (C-1301) is a change in the fight rather than a coat of paint.
   Logged per act at spawn time, so a probe reads the escalation off the
   running page instead of off this table. */
const ACT_FALL=[1,1.15,1.3],ACT_GAP=[1,0.85,0.7];
function actOf(){return t>=ACT*2?2:t>=ACT?1:0}
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const W=cv.width,H=cv.height,SHIP=22;
let ship,shots,foes,stars,score,kills,wave,t,state,fire,spawnIn,actSpawn,actVy,debris;
/* Permanence (§23, C-1374): a downed hull does not just vanish - chunks
   of it fall out of the fight, the shell-casing of a game with no floor:
   the trace crosses the sky instead of resting on it. Falling chunks are
   motion, so REDUCED keeps none; the burst is still there for the hit
   itself. draw() and wreckFacts() read the same WRECK_A. */
const WRECK_A=0.5;
function wreckSpawn(f){if(REDUCED)return;
  for(let i=0;i<3;i++){debris.push({x:f.x+(i-1)*6,y:f.y,
    vx:(i-1)*0.7,vy:1.2+i*0.6,r:5-(i%2)*2,rot:i*2.1})}}
function wreckFacts(){return {alpha:WRECK_A,
  debris:debris.map(d=>({x:d.x,y:d.y}))}}
function reset(){ship={x:W/2,y:H-34,hp:3,cool:0,kvx:0,rk:0,mz:0,sq:1};shots=[];foes=[];debris=[];score=0;kills=0;wave=0;
  t=0;state='play';fire=false;rs=(SEED>>>0)||1;
  spawnIn=Math.round(WAVE);actSpawn=[0,0,0];actVy=[0,0,0];grazeReset();
  /* A new go starts at x1. Carrying a run across a restart would hand
     the next round a head start nobody flew for (C-1411). */
  comboMiss();
  stars=[];for(let i=0;i<48;i++){stars.push({x:rand()*W,y:rand()*H,s:0.4+rand()*1.4})}}
/* A formation, not a scatter: rows read as a wave the player can answer. */
function spawn(){wave++;const a=actOf(),n=3+Math.floor(rand()*4),gap=W/(n+1),
  drop=0.35+rand()*0.35,sway=rand()<0.5?-1:1,vy=FALL*(0.8+drop)*ACT_FALL[a];
  actSpawn[a]++;actVy[a]+=vy;
  for(let i=0;i<n;i++){foes.push({x:gap*(i+1),y:-24-((i%2)*18),
    vy:vy,vx:sway*(0.2+rand()*0.5),r:13,hp:1})}}
const keys={};
addEventListener('keydown',e=>{keys[e.key.toLowerCase()]=true;
  if(e.code==='Space'){e.preventDefault();
    if(state==='play'){fire=true}else{reset()}}
  if(e.key==='r'||e.key==='R'){reset()}});
addEventListener('keyup',e=>{keys[e.key.toLowerCase()]=false;
  if(e.code==='Space'){fire=false}});
cv.addEventListener('pointerdown',()=>{if(state==='play'){fire=true}else{reset()}});
cv.addEventListener('pointerup',()=>{fire=false});
function shoot(){if(ship.cool>0)return;ship.cool=9;
  /* The gun kicks (§1×§23 事実 3, C-1380): three pixels of recoil the
     shot pushes back through the hull, gone in a third of a second.
     Motion, so reduced keeps the ship perfectly still. */
  if(!REDUCED){ship.rk=3;ship.mz=2}
  shots.push({x:ship.x,y:ship.y-16});sfx('fire')}
function step(rt){const now=performance.now();
  /* The world advances on real time, not on this display's refresh
     rate (§26, C-1608 — the gate C-1607 built and racing proved).
     Drawing is NOT gated: a 120Hz screen still gets 120 pictures a
     second, the world just stops happening twice as fast. */
  if(!TICK(rt)){draw(now);return requestAnimationFrame(step)}
  combat(state==='play'&&gateState()==='playing');
  if(state==='play'){t++;
    if(ship.cool>0)ship.cool--;
    if(keys['arrowleft']||keys['a']){ship.x=Math.max(SHIP,ship.x-4)}
    if(keys['arrowright']||keys['d']){ship.x=Math.min(W-SHIP,ship.x+4)}
    /* Knockback (§1, C-1361): the ram throws the ship AWAY from the hull,
       played out by the shared part through the same bounds the arrows
       respect. Kept under REDUCED - position is gameplay, not decoration. */
    partsThrowX(ship,SHIP,W-SHIP);
    /* the recoil settles the way it arrived: fast and small (C-1380) */
    ship.rk*=0.7;if(ship.rk<0.2)ship.rk=0;
    if(ship.mz>0)ship.mz--;
    if(fire)shoot();
    if(--spawnIn<=0){spawn();spawnIn=Math.max(8,Math.round(WAVE*ACT_GAP[actOf()]))}
    shots.forEach(s=>{s.y-=7});
    shots=shots.filter(s=>s.y>-10);
    foes.forEach(f=>{f.y+=f.vy;f.x+=f.vx;
      if(f.x<f.r||f.x>W-f.r){f.vx*=-1}});
    /* Hits first, then the ship: a foe that reaches the ship and is shot on
       the same frame should not both kill and die. */
    shots.forEach(s=>{foes.forEach(f=>{
      if(f.hp>0&&Math.hypot(f.x-s.x,f.y-s.y)<f.r+4){
        /* The run is worth what it is worth at the moment it pays out
           (C-1405's rule, C-1411's second template). Asked once, so the
           points added and the number drawn cannot disagree. `kills` stays
           the raw count because 「撃墜 N 機」 is a count. */
        f.hp=0;s.y=-99;kills++;score+=scorePop(f.x,f.y,comboHit());
        sfx('hurt',1,f.x/W);shake(4);burst(f.x,f.y,12,'ACCENT_JUICE');
        wreckSpawn(f)}})});
    foes.forEach(f=>{if(f.hp<=0)return;
      /* One distance, one radius, two answers (C-1406). The kill radius is
         unchanged and the band sits strictly outside it, so brushing a hull
         is harder than keeping away from it - never easier. */
      const gd=Math.hypot(f.x-ship.x,f.y-ship.y),gk=f.r+SHIP*0.6;
      if(gd<gk){
      /* One hull, two independent losses: the graze run and the kill
         run both end, and neither is the other's number (C-1411). */
      f.hp=0;ship.hp--;comboMiss();sfx('clash');shake(11);hitstop(5);
      wreckSpawn(f);
      ship.kvx=(ship.x<f.x?-1:1)*7;
      /* Squash & stretch, the rammed side (§1, C-1601): the heaviest hit
         in any of the ten templates - shake 11, five frames of hitstop,
         a knockback - and the only body it left the shape of untouched.
         0.7 and the quarter-step settle are racing's numbers (C-1332),
         because this is the same event: something solid hit the hull.
         Under REDUCED the silhouette never changes, the rule the recoil
         and the muzzle flash above already follow - the knockback stays
         either way, since position is gameplay and not decoration. */
      if(!REDUCED){ship.sq=0.7}
      grazeStruck(gd,gk);grazeLost();
      burst(ship.x,ship.y,18,'ALERT_JUICE');
      if(ship.hp<=0){state='over';failBeat(ship.x,ship.y)}}
      else{grazeNear(f,gk,gd,(f.x+ship.x)/2,(f.y+ship.y)/2)}});
    foes=foes.filter(f=>f.hp>0&&f.y<H+30);
    shots=shots.filter(s=>s.y>-10);
    stars.forEach(s=>{s.y+=REDUCED?0:s.s;if(s.y>H){s.y=0;s.x=rand()*W}})}
  /* Wreckage falls outside the play gate too: an 'over' screen where the
     chunks freeze mid-air would read as a bug, not a consequence. */
  debris.forEach(d=>{d.x+=d.vx;d.y+=d.vy;d.rot+=0.15});
  debris=debris.filter(d=>d.y<H+20);
  /* The hull settles by quarter-steps and snaps, outside the play gate
     for the wreckage's reason: a ship frozen mid-crush on the 'over'
     screen would read as a bug (C-1601, racing's C-1332 line). */
  ship.sq+=(1-ship.sq)*0.25;if(Math.abs(ship.sq-1)<0.01)ship.sq=1;
  draw(now);requestAnimationFrame(step)}
function draw(now){
  /* The act is read off the play clock, not the wave count: the round is
     time-boxed (C-1104), so thirds of the clock are thirds of the go at
     every difficulty. Mood only - the ship, the foes and the shots keep
     their information colours and their shapes (§4). */
  setScene(actOf());
  cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(0,0,W,H);
  /* Far first, then near, so a slow star never sits over a fast one. */
  cx.fillStyle=scenePaint('BORDER_TOKEN');
  cx.globalAlpha=FAR_A;
  stars.forEach(s=>{if(s.s<NEAR)cx.fillRect(s.x,s.y,s.s,s.s*2)});
  cx.globalAlpha=1;
  stars.forEach(s=>{if(s.s>=NEAR)cx.fillRect(s.x,s.y,s.s,s.s*2)});
  /* The wreckage under everything alive: a trace, not an actor (§23). */
  cx.globalAlpha=WRECK_A;cx.fillStyle='MAGENTA_TOKEN';
  debris.forEach(d=>{cx.save();cx.translate(d.x,d.y);cx.rotate(d.rot);
    cx.fillRect(-d.r/2,-d.r/2,d.r,d.r);cx.restore()});
  cx.globalAlpha=1;
  cx.fillStyle='CYAN_TOKEN';
  /* The trail (§1, C-1389): the third particle sibling after smoke and
     debris. Two tapering afterimages the shot's own velocity dictates -
     +7 and +14 behind, fading - so speed stays on screen for more than
     one frame. Motion, so reduced motion draws the head alone. */
  shots.forEach(s=>{cx.fillRect(s.x-1.5,s.y-8,3,10);
    if(!REDUCED){cx.globalAlpha=0.26;cx.fillRect(s.x-1,s.y+2,2,7);
      cx.globalAlpha=0.12;cx.fillRect(s.x-0.5,s.y+9,1,7);cx.globalAlpha=1}});
  /* Foes read by shape as well as colour (C-1018): a hull with a notch. */
  foes.forEach(f=>{sprite('foe',f.x-f.r,f.y-f.r,f.r*2,f.r*2,'');
    cx.fillStyle='MAGENTA_TOKEN';cx.beginPath();
    cx.moveTo(f.x,f.y+f.r);cx.lineTo(f.x-f.r,f.y-f.r*0.6);
    cx.lineTo(f.x,f.y-f.r*0.1);cx.lineTo(f.x+f.r,f.y-f.r*0.6);
    cx.closePath();cx.fill()});
  const flick=FRAME(3,14,now);
  /* The whole hull rides the recoil (C-1380): nose, wings and flame
     together, so the kick reads as the body moving, not a glitch. */
  const sy=ship.y+ship.rk;
  /* One transform for the whole hull (§1, C-1601): nose, wings, flame and
     the muzzle flash below all crush together, anchored at the tail line
     so the ship squats instead of sinking through itself. At sq=1 every
     coordinate is bit-identical to the old literals - racing's C-1385
     contract, same shape. */
  const ssq=ship.sq,ssw=2-ssq,BY=sy+SHIP*0.7;
  const SX=dx=>ship.x+dx*ssw,SY=y=>BY+(y-BY)*ssq;
  cx.fillStyle='RAISED_TOKEN';
  cx.beginPath();cx.moveTo(SX(0),SY(sy-SHIP));
  cx.lineTo(SX(-SHIP*0.8),SY(sy+SHIP*0.7));
  cx.lineTo(SX(SHIP*0.8),SY(sy+SHIP*0.7));cx.closePath();cx.fill();
  cx.fillStyle='CYAN_TOKEN';
  cx.fillRect(SX(-3),SY(sy+SHIP*0.7),6*ssw,(6+flick*3)*ssq);
  /* Muzzle flash (§1×§23 事実 4, C-1391): the middle of the talk's
     shot trio [10:13-10:58]. Two frames of light at the nose, the same
     !REDUCED event as the kick. (Worded without the b-word on purpose:
     the graze test reads 「no enemy shots」 off this page's text.) */
  if(ship.mz>0){cx.globalAlpha=0.85;
    cx.fillRect(SX(-3),SY(sy-SHIP-6),6*ssw,6*ssq);cx.globalAlpha=1}
  cx.fillStyle='MAGENTA_TOKEN';
  for(let i=0;i<ship.hp;i++){cx.fillRect(12+i*18,10,14,10)}
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(W-208,6,204,54);cx.globalAlpha=1;
  cx.fillStyle=HUD_INK;cx.font='13px ui-monospace,monospace';
  /* The graze run is on screen while it is worth something: a risk the
     player cannot see the state of is a gamble, not a decision. */
  const gz=grazeFacts();
  /* The multiplier is drawn at x1 as much as at x4, and the raw count
     stays beside the points so 「得点」 and 「撃墜」 cannot be confused. */
  cx.fillText('得点 '+score+' '+comboLabel()+'  第 '+wave+' 波',W-200,19);
  cx.fillText('撃墜 '+kills,W-200,55);
  cx.fillText('かすり '+gz.paid+'  '+'・'.repeat(gz.run)+'－'.repeat(gz.need-gz.run),W-170,37);
  if(state==='over'){cx.fillStyle='SCRIM_TOKEN'+'d0';cx.fillRect(0,0,W,H);
    cx.fillStyle='INK_TOKEN';cx.font='20px ui-monospace,monospace';
    const a='撃墜 '+kills+' 機・得点 '+score+'。';cx.fillText(a,W/2-a.length*10,H/2-8);
    cx.font='13px ui-monospace,monospace';
    if((typeof roundAskReady!=='function'||roundAskReady())){const b='SPACE か R、タップでもう一度';cx.fillText(b,W/2-b.length*6.5,H/2+18)}}}
/* Read back off the running page rather than grepped for: the act the sky
   is in, and the nearest incoming hull, so a probe can dodge like a hand. */
function shooterFacts(){const incoming=[];
  foes.forEach(f=>{if(f.hp>0&&f.y>ship.y-170){incoming.push([f.x,f.y])}});
  return {t:t,wave:wave,scene:SCENE,hp:ship.hp,state:state,score:score,
    kills:kills,combo:comboFacts(),
    graze:grazeFacts(),kill:foes.length?foes[0].r+SHIP*0.6:null,
    x:ship.x,w:W,incoming:incoming,act:actOf(),
    actSpawn:actSpawn.slice(),actVy:actVy.slice()}}
reset();step();
"""

#: The page driven in node, the same no-op browser the racing probe built:
#: the fight is flown through all three acts so the sky's act changes can
#: be read off the running page instead of trusted from the palette table.
#: The pilot holds fire and sidesteps the nearest incoming hull - dodging,
#: not luck, is what carries three hit points across two thousand frames.
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
/* One clock across every run() call: the round preamble reads the frame
   timestamp, and a clock that restarted at zero would hold its ROUND_T0
   forever. */
let F = 0;
/* Which act the page was actually IN, in the order it went (C-1645).
   sceneFacts().scenes is the palette TABLE - three colours that exist -
   and the contract read only that, so a page pinned to act 0 passed it
   (C-1640 proved that with a destruction). SCENE is the preamble's own
   variable, set by draw(), so sampling it after each frame costs nothing
   and reports the acts as they happened. */
const sceneOrder = [];
function sceneTick(){
  if (typeof SCENE === 'number' && sceneOrder[sceneOrder.length - 1] !== SCENE) {
    sceneOrder.push(SCENE) } }
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16); sceneTick() } }
function key(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
/* Past the briefing: the gate holds every frame until pressed. */
key('keydown', ' '); key('keyup', ' ');
run(2);
const early = shooterFacts();
/* Fly the round: hold fire, sidestep whatever is closing in, and note the
   act of the sky as each third of the clock arrives. */
key('keydown', ' ');
let sceneMid = null;
while (shooterFacts().state === 'play' && shooterFacts().t < 3480) {
  const f = shooterFacts();
  if (f.t >= 1300 && f.t < 2400 && sceneMid === null) sceneMid = f.scene;
  key('keyup', 'ArrowLeft'); key('keyup', 'ArrowRight');
  /* Two jobs, in priority order. Dodge: only hulls at the ship's own
     altitude can hit it, so those are the ones that pick the lane - and a
     lane is no good if getting there means crossing one of them. Hunt:
     with nothing imminent, sit under the lowest hull so the held trigger
     thins the field; a pilot that only dodged let the sky saturate. */
  const im = f.incoming.filter(([fx, fy]) => fy > 226 && fy < 330);
  let goal = null;
  if (im.some(([fx]) => Math.abs(fx - f.x) < 40)) {
    let bestClear = -1e9, bestSafe = null, best = f.x;
    for (let x = 26; x <= f.w - 26; x += 8) {
      let clear = 1e9;
      im.forEach(([fx]) => { clear = Math.min(clear, Math.abs(x - fx)) });
      const lo = Math.min(f.x, x), hi = Math.max(f.x, x);
      const blocked = im.some(([fx]) => fx > lo - 28 && fx < hi + 28);
      const score = Math.min(clear, 120) - Math.abs(x - f.x) * 0.02;
      if (score > bestClear) { bestClear = score; best = x }
      if (!blocked && (bestSafe === null || score > bestSafe[1])) bestSafe = [x, score];
    }
    goal = bestSafe ? bestSafe[0] : best;
  } else {
    let ty = -1;
    f.incoming.forEach(([fx, fy]) => { if (fy <= 226 && fy > ty) { ty = fy; goal = fx } });
  }
  if (goal !== null && goal < f.x - 4) key('keydown', 'ArrowLeft');
  else if (goal !== null && goal > f.x + 4) key('keydown', 'ArrowRight');
  run(1);
}
const end = shooterFacts();
const palette = sceneFacts();
const hud = hudFacts();
console.log(JSON.stringify({
  sceneOrder: sceneOrder,
  scenes: palette.scenes,
  hud: hud,
  depth: depthFacts(),
  sceneEarly: early.scene, sceneMid: sceneMid, sceneLate: end.scene,
  t: end.t, wave: end.wave, hp: end.hp, score: end.score, state: end.state,
  /* Escalation, as measured: waves counted per act at spawn time, and the
     descent speed each act actually shipped (C-1302). */
  actSpawn: end.actSpawn,
  actVyAvg: end.actVy.map((v, i) => end.actSpawn[i] ? v / end.actSpawn[i] : 0),
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the fight can be flown in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)

#: The knockback, as played (§1, C-1361). A hull is placed on the ship's
#: shoulder and the ram's throw is read off kbFacts() frame by frame:
#: away from the hull, settled inside half a second, and pinned by the
#: screen bound rather than pushed through it.
KB_PROBE = """
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
key(' ');
run(4);
const x0 = ship.x, hpBefore = ship.hp;
foes.push({ x: ship.x + 3, y: ship.y, vy: 0, vx: 0, r: 13, hp: 1 });
run(1);
const onHit = kbFacts();
const track = [];
for (let i = 0; i < 40; i++){ run(1); track.push(kbFacts().x) }
const settled = kbFacts();
/* The wall case: parked on the left bound with the hull to the right,
   the throw points into the wall and the bound must hold. */
foes.length = 0; ship.x = SHIP; ship.kvx = 0; ship.hp = 3;
foes.push({ x: ship.x + 3, y: ship.y, vy: 0, vx: 0, r: 13, hp: 1 });
run(1);
let minX = 1e9;
for (let i = 0; i < 40; i++){ run(1); minX = Math.min(minX, kbFacts().x) }
console.log(JSON.stringify({
  x0: x0, hpBefore: hpBefore, onHit: onHit,
  moved: x0 - Math.min.apply(null, track),
  settledKvx: settled.kvx, hpAfter: settled.hp, minX: minX, bound: SHIP,
}));
"""


def kb_probe(script: str) -> str:
    """The page's own script, wrapped so the throw can be measured."""

    return KB_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The rammed hull, watched frame by frame (§1, C-1601). A real ram, then
#: the crush read off kbFacts every frame - and, because a number that
#: never reaches the paint is not a deformation, a recording context that
#: keeps the hull triangle's own points so the drawn silhouette can be
#: shown to change with it. Flying and firing untouched must leave the
#: shape alone, and under reduced motion the ram must not bend it at all.
SQUASH_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
let PTS = [], HULL = null;
const CTX = { globalAlpha: 1, fillStyle: '', strokeStyle: '', lineWidth: 1,
  font: '', textAlign: '', globalCompositeOperation: '', lineJoin: '',
  lineCap: '', shadowBlur: 0, shadowColor: '' };
const STACK = [];
const rec = new Proxy(CTX, {
  get(t, k){
    if (k in t && typeof t[k] !== 'function') return t[k];
    if (k === 'save') return () => { STACK.push(Object.assign({}, CTX)) };
    if (k === 'restore') return () => { Object.assign(CTX, STACK.pop() || {}) };
    if (k === 'beginPath') return () => { PTS = [] };
    if (k === 'moveTo' || k === 'lineTo') return (x, y) => { PTS.push([x, y]) };
    /* The hull is the only three-point path the page draws - a foe is
       four - so it is picked out by shape, not by a token name this
       wrapper is not built to substitute. */
    if (k === 'fill') return () => { if (PTS.length === 3) HULL = PTS.slice() };
    if (k === 'createLinearGradient' || k === 'createRadialGradient')
      return () => ({ addColorStop(){} });
    if (k === 'measureText') return () => ({ width: 10 });
    return () => undefined },
  set(t, k, v){ t[k] = v; return true } });
/* Only the motion query answers yes. A stub that says yes to everything
   also turns the touchpad on (pointer:coarse), and its buttons put more
   three-point paths on the canvas - which would be read as the hull. */
globalThis.matchMedia = (q) =>
  ({ matches: REDUCED_INPUT && /reduce/.test(String(q)) });
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
function key(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
function span(){ if (!HULL) return null;
  const xs = HULL.map(p => p[0]), ys = HULL.map(p => p[1]);
  return { w: Math.max.apply(null, xs) - Math.min.apply(null, xs),
    h: Math.max.apply(null, ys) - Math.min.apply(null, ys) } }
key('keydown', ' '); key('keyup', ' ');
run(4);
/* First: fly and fire, untouched. Nothing here may bend the hull - the
   recoil moves it, the muzzle flash lights it, neither deforms it. */
key('keydown', 'ArrowLeft');
/* Space stays DOWN for the whole stretch: the gun has a nine-frame
   cooldown, so forty frames of held fire is four real shots and four
   real recoils. Steering without shooting would let a crush wired into
   shoot() go unnoticed. */
key('keydown', ' ');
let restSq = [], restSpan = [], restShots = 0;
for (let i = 0; i < 40; i++){ run(1); restSq.push(kbFacts().sq);
  if (kbFacts().rk > 0) restShots++;
  const s = span(); if (s) restSpan.push(Math.round(s.w * 1e6) / 1e6) }
key('keyup', ' '); key('keyup', 'ArrowLeft');
const restShape = restSpan.length ? restSpan[0] : null;
/* Now the ram. */
foes.push({ x: ship.x + 3, y: ship.y, vy: 0, vx: 0, r: 13, hp: 1 });
run(1);
const hitSq = kbFacts().sq, hitShape = span();
const track = [];
for (let i = 0; i < 30; i++){ run(1); track.push(kbFacts().sq) }
const settled = kbFacts().sq;
console.log(JSON.stringify({
  hp: kbFacts().hp,
  restSq: Array.from(new Set(restSq)).sort(),
  restShapes: Array.from(new Set(restSpan)).length,
  restShots: restShots,
  hitSq: hitSq,
  settled: settled,
  settledIn: track.findIndex(v => v === 1),
  restW: restShape, hitW: hitShape ? hitShape.w : null,
  hitH: hitShape ? hitShape.h : null,
  reduced: REDUCED_INPUT
}));
"""


def squash_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the ram's crush can be watched."""

    return SQUASH_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The gun's kick, watched frame by frame (§1×§23 事実 3, C-1380): one
#: real shot must push the hull back three pixels and settle fast; under
#: reduced motion the same shot moves nothing.
KICK_PROBE = """
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
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
ev('keydown', ' '); ev('keyup', ' ');
run(4);
const idle = kbFacts().rk;
/* One held trigger, one frame: the shot and its kick. */
ev('keydown', ' ');
run(1);
const onFire = kbFacts().rk;
ev('keyup', ' ');
const trace = [];
for (let i = 0; i < 10; i++){ run(1); trace.push(kbFacts().rk) }
console.log(JSON.stringify({ idle: idle, onFire: onFire, trace: trace,
  shots: shots.length }));
"""


def kick_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the recoil can be watched."""

    return KICK_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The trail, as painted (§1, C-1389): a recording context that tracks
#: globalAlpha pairs every fill with the opacity it was drawn at, one real
#: shot flies, and every flight frame must show the full-alpha head with
#: two fading afterimages exactly one and two flight-steps behind. Under
#: reduced motion the same shot flies with the head alone.
TRAIL_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
let A = 1, frameFills = [];
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy({
    fillRect: (x, y, w, h) => { frameFills.push([x, y, w, h, A]) } }, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: (t, k, v) => { if (k === 'globalAlpha') A = v; return true } }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
ev('keydown', ' '); ev('keyup', ' ');
run(4);
ev('keydown', ' '); run(1); ev('keyup', ' ');
const fired = shots.length;
let watched = 0, headFrames = 0, fullTrail = 0, ghosts = 0;
for (let i = 0; i < 20 && shots.length; i++) {
  frameFills = []; run(1);
  const s = shots[0]; if (!s) break; watched++;
  if (frameFills.some(f => f[0] === s.x - 1.5 && f[1] === s.y - 8 &&
    f[2] === 3 && f[3] === 10 && f[4] === 1)) headFrames++;
  const t1 = frameFills.some(f => f[0] === s.x - 1 && f[1] === s.y + 2 &&
    f[2] === 2 && f[3] === 7 && f[4] === 0.26);
  const t2 = frameFills.some(f => f[0] === s.x - 0.5 && f[1] === s.y + 9 &&
    f[2] === 1 && f[3] === 7 && f[4] === 0.12);
  if (t1 && t2) fullTrail++;
  ghosts += frameFills.filter(f => (f[4] === 0.26 || f[4] === 0.12) &&
    Math.abs(f[0] - s.x) < 4).length;
}
console.log(JSON.stringify({ fired: fired, watched: watched,
  headFrames: headFrames, fullTrail: fullTrail, ghosts: ghosts }));
"""


def trail_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the shot's trail can be watched."""

    return TRAIL_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The muzzle flash, as painted (§1×§23 事実 4, C-1391): one real shot
#: must light the nose for exactly two frames at 0.85 alpha, and reduced
#: motion fires the same shot with the nose dark.
MUZZLE_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
let A = 1, frameFills = [];
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy({
    fillRect: (x, y, w, h) => { frameFills.push([x, y, w, h, A]) } }, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: (t, k, v) => { if (k === 'globalAlpha') A = v; return true } }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
function flashNow(){ return frameFills.some(f => f[2] === 6 && f[3] === 6 &&
  f[4] === 0.85 && f[0] === ship.x - 3 &&
  f[1] === ship.y + ship.rk - SHIP - 6) }
ev('keydown', ' '); ev('keyup', ' ');
run(4);
frameFills = []; run(1);
const idleFlash = flashNow();
ev('keydown', ' ');
const lit = [];
for (let i = 0; i < 4; i++) { frameFills = []; run(1); lit.push(flashNow()) }
ev('keyup', ' ');
console.log(JSON.stringify({ shots: shots.length, idleFlash: idleFlash,
  lit: lit }));
"""


def muzzle_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the nose light can be watched."""

    return MUZZLE_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The kill, heard where it happened (§2 増築, C-1394): two engineered
#: kills - one right of centre, one left - and the recorded pan values
#: must match (x/W*2-1)*0.8 in sign and to the digit, while everything
#: fired before them (start chirp included) built no panner at all.
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
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
ev('keydown', ' '); ev('keyup', ' ');
run(4);
const before = pans.length;
foes.length = 0;
foes.push({ x: 600, y: 200, vy: 0, vx: 0, r: 13, hp: 1 });
shots.push({ x: 600, y: 205 });
run(1);
foes.push({ x: 120, y: 200, vy: 0, vx: 0, r: 13, hp: 1 });
shots.push({ x: 120, y: 205 });
run(1);
const expected = [(600 / W * 2 - 1) * 0.8, (120 / W * 2 - 1) * 0.8];
console.log(JSON.stringify({ before: before, kills: kills,
  pans: pans, expected: expected }));
"""


def pan_probe(script: str) -> str:
    """The page's own script, wrapped so the kill's stereo position can
    be read off the audio graph."""

    return PAN_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: A kill, then gravity (§23, C-1374): the chunks appear where the hull
#: died, fall every frame, and drain once they leave the screen. Under
#: reduced motion nothing is spawned at all.
WRECK_PROBE = """
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
key(' ');
run(4);
/* One hull, one shot, same spot: a certain kill. */
foes.push({ x: 200, y: 80, vx: 0, vy: 0.4, r: 13, hp: 1 });
shots.push({ x: 200, y: 80 });
run(1);
const w0 = wreckFacts();
const y0 = w0.debris.map(d => d.y);
run(30);
const y1 = wreckFacts().debris.map(d => d.y);
/* Long enough for every chunk to cross the bottom and drain. */
run(400);
const drained = wreckFacts().debris.length;
console.log(JSON.stringify({
  spawned: w0.debris.length, y0: y0, y1: y1,
  drained: drained, alpha: w0.alpha,
}));
"""


def wreck_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the falling chunks can be watched."""

    return WRECK_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


__all__ = [
    "KB_PROBE",
    "SQUASH_PROBE",
    "squash_probe",
    "KICK_PROBE",
    "TRAIL_PROBE",
    "MUZZLE_PROBE",
    "PAN_PROBE",
    "kick_probe",
    "trail_probe",
    "muzzle_probe",
    "pan_probe",
    "kb_probe",
    "WRECK_PROBE",
    "wreck_probe",
    "SHOOTER_DIFFICULTY",
    "SHOOTER_HOW",
    "SHOOTER_SCRIPT",
    "SHOOTER_TITLE",
    "SHOOTER_WORDS",
    "PROBE",
    "probe_source",
]
