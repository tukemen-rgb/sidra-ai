"""The energy-duel template - the beam clash the second video showed.

「ドラゴンボールのゲーム作って」 came with footage of the moment that matters
in that genre: two fighters, a charged blast, the beams meeting in the middle
and the struggle over where the meeting point goes. That moment is the whole
template. Charge by holding, release to fire, and when both beams are out the
clash point is pushed by mashing - the thing every playground version of this
game was about.

Same deal as the adventure template on names: the *genre* is buildable, the
franchise is not ours. The fighters are silhouettes with auras in the house
palette, the title guard in ``games.generate_game`` swaps a trademarked title
out and says so, and nothing on the page claims otherwise.

Token contract, shared with every template: ``SPEED_TOKEN`` is the CPU's
charge-speed multiplier, ``BAND_TOKEN`` the frames between CPU decisions,
``SEED_TOKEN`` drives the CPU's behaviour pattern so the same request is the
same opponent. ``REDUCED``/``ease``/``FRAME`` come from the animation
preamble: the aura shimmer and clash sparks freeze under reduced motion, the
duel itself keeps working.
"""

from __future__ import annotations

#: Words that pick this template. The franchise names are detection-only -
#: they route the request to the right genre and are never printed by the
#: page; what happens to the *title* is the trademark guard's job.
DUEL_WORDS: tuple[str, ...] = (
    "ドラゴンボール",
    "ビーム",
    "エネルギー波",
    "気弾",
    "撃ち合い",
    "対戦",
    "バトル",
    "必殺技",
    "duel",
    "versus",
    "battle",
    "dragon ball",
)

#: (CPU charge-speed multiplier, frames between CPU decisions).
DUEL_DIFFICULTY: dict[str, tuple[float, float]] = {
    "easy": (0.7, 90),
    "normal": (1.0, 60),
    "hard": (1.4, 40),
}

DUEL_TITLE = "ひかりの押し合い"
DUEL_HOW = (
    "SPACE か長押しでチャージ、離してビーム発射。↑↓ でレーン移動。"
    "ビーム同士がぶつかったら SPACE 連打で押し返す。先に 3 発当てた方の勝ち。M で消音。"
)

DUEL_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const CSPEED=SPEED_TOKEN,CTHINK=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const LANES=[80,160,240],PX=110,EX=610;
/* The opponent's temperament, fixed by the request: the same words are the
   same fight, so a player can learn one and come back to it. A quick draw
   throws thin beams constantly; a charger waits and swings a wide one. The
   counter-play is opposite in each case, which is the point. */
const CPU_STYLE=((SEED>>>3)&1)?'quick':'charger';
const CPU_FIRE=CPU_STYLE==='quick'?[22,26]:[62,50];
const CPU_THINK=CPU_STYLE==='quick'?0.6:1.3;
/* Holding at maximum is no longer free. Past this many frames at full the
   charge goes off in your own hands - which is what makes "let go" a
   decision rather than a formality. */
const OVER_LIMIT=48,STUN_FRAMES=90;
/* How many frames before its shot the opponent's aim LOCKS (C-1309). The
   telegraph used to say only *when*: the lane was re-rolled onto the
   player at the trigger, which no human reaction (12-15 frames, the
   number C-1022 itself measured) could answer. Eighteen frames of locked,
   visible aim is what turns "read the aura" from a promise into a rule. */
const AIM_LOCK=18;
/* §6's second-half change (C-1318), duel edition: the guardian and the
   kaiju both quicken past half health, but this - the only versus mode -
   used to volley at the same pace at match point as at the opening bell.
   The act is how close anyone is to losing: both fresh, first blood,
   match point. The foe's charge fills faster and its pauses shrink by
   the same multipliers the shooter's and marble's acts use; the player's
   own charge is untouched (the boss changes, your sword does not), and
   the aim-lock offset scales WITH the rate so the locked telegraph is
   exactly AIM_LOCK frames of wall-clock warning in every act (C-1309). */
const TENSE=[1,1.15,1.3];
/* The same act paints the arena (§7, C-1321): the sky the tempo already
   knows. Lanes, auras and beams keep their information colours (§4). */
setPal(DUEL_PAL_TOKEN);
/* HUD contract (§4 WCAG 1.4.3, C-1334): draw() paints the HUD through
   these constants and hudFacts() reports them, so the metric can blend
   the plate over every measured sky the way the canvas does. The plate
   is the untinted theme surface at 0.7: the brightest final act was
   sinking the themed ink to ~3:1 here too (C-1329's fix, more templates). */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A}}
function duelAct(){if(!p||!e)return 0;
  const low=Math.min(p.hp,e.hp);
  return low<=1?2:(p.hp<3||e.hp<3)?1:0}
function tempo(){return TENSE[duelAct()]}
let p,e,state,winner,flash,spark,mash;
function fighter(x){return {x:x,lane:1,hp:3,charge:0,beam:0,beamLane:1,hold:false,
  think:0,hitLock:false,over:0,stun:0,aim:-1,fireAt:0}}
function duelFacts(){return {style:CPU_STYLE,fire:CPU_FIRE,overLimit:OVER_LIMIT,
  act:duelAct(),tense:TENSE.slice(),
  playerStun:p?p.stun:0,playerOver:p?p.over:0,enemyStun:e?e.stun:0,
  aim:e?e.aim:-1,aimLock:AIM_LOCK,enemyHold:e?e.hold:false,
  enemyCharge:e?e.charge:0,enemyFireAt:e?e.fireAt:0,
  enemyBeam:e?e.beam:0,enemyBeamLane:e?e.beamLane:-1,
  pLane:p?p.lane:-1,pHp:p?p.hp:0,eHp:e?e.hp:0}}
function overload(f){f.stun=STUN_FRAMES;f.hold=false;f.charge=0;f.over=0;
  sfx('hurt');shake(9);hitstop(4);burst(f.x,LANES[f.lane],16,'ALERT_JUICE')}
function reset(){p=fighter(PX);e=fighter(EX);state='play';winner='';flash=0;spark=0;mash=0;
  rs=(SEED>>>0)||1}
addEventListener('keydown',ev=>{
  if(ev.code==='Space'){ev.preventDefault();
    if(state!=='play'){reset();return}
    if(p.stun>0)return;
    if(p.beam>0&&e.beam>0){mash+=3;sfx('clash')}else{if(!p.hold){sfx('charge')}p.hold=true}}
  if(p.stun<=0&&ev.key==='ArrowUp'&&p.lane>0){p.lane--}
  if(p.stun<=0&&ev.key==='ArrowDown'&&p.lane<2){p.lane++}
  if(ev.key==='r'||ev.key==='R'){reset()}});
addEventListener('keyup',ev=>{if(ev.code==='Space'){fire(p)}});
cv.addEventListener('pointerdown',()=>{if(state!=='play'){reset();return}
  if(p.stun>0)return;
  if(p.beam>0&&e.beam>0){mash+=3;sfx('clash')}else{if(!p.hold){sfx('charge')}p.hold=true}});
cv.addEventListener('pointerup',()=>{fire(p)});
function fire(f){if(state!=='play'||!f.hold||f.stun>0)return;f.hold=false;f.over=0;
  if(f.charge>18){f.beam=f.charge;f.beamLane=f.lane;if(flashGate())flash=1;sfx('fire');
    /* the kick scales with the charge: a tap fires a thread, a long hold
       fires something that shoves the camera */
    shake(2+f.charge*0.08);burst(f.x,LANES[f.lane],10,'ACCENT_JUICE');
    /* the duel's one honest rule: the hit is decided the moment the trigger
       is pulled. Dodging happens by reading the charge - the visibly growing
       aura - not by outrunning a beam that hangs for 20-47 frames while
       human reaction needs 12-15. Measured before fixed (C-1022). */
    const foe=(f===p)?e:p;f.hitLock=(foe.lane===f.beamLane)}
  f.charge=0}
function cpu(){if(e.stun>0){e.stun--;return}
  e.think--;
  if(e.think<=0){e.think=(CTHINK+rand()*CTHINK)*CPU_THINK/tempo();
    const move=rand();
    /* A body that wandered off its own locked sightline would make the
       telegraph a lie twice over, so thinking moves only while unaimed. */
    if(e.aim<0){
      if(move<0.45){e.lane=p.lane}
      else if(move<0.7){e.lane=Math.floor(rand()*3)}}
    if(e.beam<=0&&!e.hold){e.hold=true;
      /* The whole volley is decided here: when it will fire, and - at
         AIM_LOCK frames before that point - where. Nothing about it is
         re-rolled at the trigger (C-1309). */
      e.fireAt=CPU_FIRE[0]+rand()*CPU_FIRE[1];e.aim=-1}}
  if(e.hold){e.charge+=0.9*CSPEED*tempo();
    /* Same rule, same fighter: an opponent immune to the overload would be
       a penalty on the player rather than a rule of the game. */
    if(e.charge>=100){e.over++;if(e.over>OVER_LIMIT){e.aim=-1;overload(e);return}}
    if(e.aim<0&&e.charge>=e.fireAt-AIM_LOCK*0.9*CSPEED*tempo()){
      e.aim=p.lane;e.lane=e.aim}
    if(e.charge>e.fireAt){e.hold=false;e.over=0;
      e.beamLane=e.aim>=0?e.aim:e.lane;e.lane=e.beamLane;
      e.hitLock=(p.lane===e.beamLane);e.aim=-1;
      e.beam=e.charge;
      e.charge=0;if(flashGate())flash=1;sfx('fire')}}}
function hit(who){who.hp--;if(flashGate())flash=1;sfx('hurt');
  shake(10);hitstop(5);burst(who.x,LANES[who.lane],18,'ALERT_JUICE');
  if(who.hp<=0){state='end';
    if(who===e){winner='勝利。ひかりが押し切った。';winBeat(EX,LANES[e.lane])}
    else{winner='敗北。もう一度。';failBeat(PX,LANES[p.lane])}}}
function step(){const now=performance.now();
  combat(state==='play'&&gateState()==='playing');
  setScene(duelAct());
  if(state==='play'){
    if(p.stun>0){p.stun--}
    if(p.hold&&p.stun<=0){p.charge=Math.min(100,p.charge+1.4);
      if(p.charge>=100){p.over++;if(p.over>OVER_LIMIT){overload(p)}}}
    cpu();
    const pB=p.beam>0,eB=e.beam>0,same=p.beamLane===e.beamLane;
    if(pB&&eB&&same){
      /* the clash: mashing feeds the player side, charge fed the CPU side */
      spark+=(mash*0.8+p.beam*0.02)-(e.beam*0.045*CSPEED);mash=Math.max(0,mash-1);
      if(spark>60){hit(e);p.beam=0;e.beam=0;spark=0}
      if(spark<-60){hit(p);p.beam=0;e.beam=0;spark=0}}
    else{
      if(pB){p.beam-=2;if(p.beam<=0){if(p.hitLock){hit(e)}p.beam=0;p.hitLock=false}}
      if(eB){e.beam-=2;if(e.beam<=0){if(e.hitLock){hit(p)}e.beam=0;e.hitLock=false}}}}
  draw(now);requestAnimationFrame(step)}
function aura(x,y,r,c,now){const s=REDUCED?0:FRAME(4,6,now);
  cx.globalAlpha=0.25;cx.fillStyle=c;
  cx.beginPath();cx.arc(x,y,r+s*2,0,6.28318);cx.fill();cx.globalAlpha=1}
function body(x,y,c,mir){
  sprite('fighter',x-12,y-26,24,44,'');
  cx.fillStyle=c;cx.fillRect(x-9,y-24,18,20);
  cx.fillRect(x-6,y-4,12,22);
  cx.fillStyle='#05070f';cx.fillRect(x-9+(mir?10:2),y-20,6,5)}
function beamDraw(f,from,dir,c,now){
  if(f.beam<=0)return;const y=LANES[f.beamLane];
  const clash=p.beam>0&&e.beam>0&&p.beamLane===e.beamLane;
  /* the picture tells the result: a landed beam stops at the target, a
     missed one sails past them off screen */
  const foeX=(dir>0)?EX-16:PX+16;
  const mid=clash?(cv.width/2+spark*3):(f.hitLock?foeX:(dir>0?cv.width:0));
  const w=6+f.beam*0.18;
  cx.fillStyle=c;cx.globalAlpha=0.9;
  const x0=dir>0?from:mid,x1=dir>0?mid:from;
  cx.fillRect(x0,y-w/2,x1-x0,w);cx.globalAlpha=1;
  cx.beginPath();cx.arc(from,y,w*0.9,0,6.28318);cx.fill();
  if(clash){const j=REDUCED?0:FRAME(3,3,now)*3;
    cx.fillStyle='#f5f7ff';cx.beginPath();
    cx.arc(cv.width/2+spark*3,y,10+j,0,6.28318);cx.fill()}}
function draw(now){
  cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(0,0,cv.width,cv.height);
  cx.fillStyle=scenePaint('RAISED_TOKEN');cx.fillRect(0,cv.height-24,cv.width,24);
  if(flash>0){cx.globalAlpha=0.5*ease(flash);cx.fillStyle='#f5f7ff';
    cx.fillRect(0,0,cv.width,cv.height);cx.globalAlpha=1;flash-=0.05}
  aura(PX,LANES[p.lane],26+p.charge*0.2,'CYAN_TOKEN',now);
  aura(EX,LANES[e.lane],26+e.charge*0.2,'MAGENTA_TOKEN',now);
  /* The locked sightline (C-1309): once the opponent has chosen its lane,
     the lane says so - a blinking dashed line, steady under reduced
     motion, with AIM_LOCK frames left to leave it. Where was the missing
     half of the telegraph; the aura still says when. */
  if(e.hold&&e.aim>=0){const ly=LANES[e.aim];
    if(REDUCED||FRAME(2,4,now)===0){
      cx.strokeStyle='MAGENTA_TOKEN';cx.lineWidth=2;
      if(cx.setLineDash)cx.setLineDash([7,7]);
      cx.beginPath();cx.moveTo(PX+30,ly);cx.lineTo(EX-30,ly);cx.stroke();
      if(cx.setLineDash)cx.setLineDash([]);cx.lineWidth=1}}
  body(PX,LANES[p.lane],'CYAN_TOKEN',true);
  body(EX,LANES[e.lane],'MAGENTA_TOKEN',false);
  beamDraw(p,PX+14,1,'CYAN_TOKEN',now);
  beamDraw(e,EX-14,-1,'MAGENTA_TOKEN',now);
  cx.fillStyle='CYAN_TOKEN';
  for(let i=0;i<p.hp;i++){cx.fillRect(16+i*18,10,14,10)}
  cx.fillStyle='MAGENTA_TOKEN';
  for(let i=0;i<e.hp;i++){cx.fillRect(cv.width-30-i*18,10,14,10)}
  if(p.charge>0||p.stun>0){cx.fillStyle='RAISED_TOKEN';cx.fillRect(16,26,104,8);
    /* The last stretch is drawn as danger, because that is what it is: the
       bar used to stop silently at full and holding there cost nothing. */
    cx.fillStyle='#00000055';cx.fillRect(18+88,28,14,4);
    cx.fillStyle=p.charge>=100?'ALERT_JUICE':'CYAN_TOKEN';
    cx.fillRect(18,28,p.charge,4);
    if(p.charge>=100){const left=Math.max(0,OVER_LIMIT-p.over);
      cx.fillStyle='ALERT_JUICE';cx.fillRect(18,36,left*100/OVER_LIMIT,2)}}
  if(p.stun>0){cx.fillStyle='ALERT_JUICE';cx.font='13px ui-monospace,monospace';
    cx.fillText('暴発。'+Math.ceil(p.stun/60)+' 秒動けない',16,50)}
  if(e.stun>0){cx.fillStyle='ALERT_JUICE';cx.font='13px ui-monospace,monospace';
    cx.fillText('相手が暴発した',cv.width-140,50)}
  /* Who you are fighting, said out loud: the counter-play to a quick draw
     is the opposite of the counter-play to a charger, and a player who
     cannot tell which one they got is guessing rather than deciding. */
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(cv.width/2-120,6,240,18);cx.globalAlpha=1;
  /* The label was a hardcoded grey-blue: 1.74:1 against the final
     act's floor, and 2.1:1 even on paper (C-1131's check only sees
     the DEFAULT ink misused, so it sailed through). The theme's own
     ink, on the plate, like every other word (C-1334). */
  cx.fillStyle=HUD_INK;cx.font='12px ui-monospace,monospace';
  cx.fillText('相手: '+(CPU_STYLE==='quick'?'早撃ち型':'溜め型'),cv.width/2-40,20)
  cx.fillStyle='INK_TOKEN';cx.font='13px ui-monospace,monospace';
  if(p.beam>0&&e.beam>0&&p.beamLane===e.beamLane){
    cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
    cx.fillRect(cv.width/2-116,30,232,18);cx.globalAlpha=1;
    cx.fillStyle=HUD_INK;
    cx.fillText('押し合い。SPACE 連打で押し返す。',cv.width/2-110,44)
    /* The push was only legible as the meeting point drifting, which is the
       thing you are already too busy to watch. A bar says how close the
       next hit is, and which way. */
    const gw=200,gx=cv.width/2-gw/2,gy=52;
    cx.fillStyle='RAISED_TOKEN';cx.fillRect(gx,gy,gw,8);
    cx.fillStyle='#00000055';cx.fillRect(gx+gw/2-1,gy,2,8);
    const at=Math.max(-1,Math.min(1,spark/60));
    cx.fillStyle=at>=0?'CYAN_TOKEN':'MAGENTA_TOKEN';
    if(at>=0){cx.fillRect(gx+gw/2,gy,at*gw/2,8)}
    else{cx.fillRect(gx+gw/2+at*gw/2,gy,-at*gw/2,8)}}
  if(state==='end'){cx.fillStyle='SCRIM_TOKEN'+'d0';cx.fillRect(0,0,cv.width,cv.height);
    cx.fillStyle='INK_TOKEN';cx.font='20px ui-monospace,monospace';
    cx.fillText(winner,cv.width/2-winner.length*10,cv.height/2-6);
    cx.font='13px ui-monospace,monospace';
    cx.fillText('SPACE / タップでもう一度',cv.width/2-78,cv.height/2+20)}}
reset();step();
"""

#: Drives the duel in node so the new rules can be observed rather than
#: read: hold forever and see whether it costs anything, and compare two
#: seeds to see whether the opponent's temperament is behaviour or decoration.
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
/* Past the start screen first: the gate holds every frame until pressed. */
const press = { key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} };
keyHandlers.forEach(fn => fn(press));
run(2);
/* Now hold the button down and never let go - the strategy that used to be
   free. p.hold is set directly because the gate swallowed the first press. */
p.hold = true;
let stunSeen = 0, peakCharge = 0;
for (let i = 0; i < 400; i++) { run(1); peakCharge = Math.max(peakCharge, p.charge);
  if (p.stun > 0) { stunSeen++ } if (p.hold === false && p.stun <= 0) { p.hold = true } }
console.log(JSON.stringify({
  style: duelFacts().style, fire: duelFacts().fire, overLimit: duelFacts().overLimit,
  stunFrames: stunSeen, peakCharge: peakCharge, hp: p.hp,
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the duel can be played in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The telegraph, held to its word (C-1309): once the aim locks, the shot
#: goes where the line said, at least AIM_LOCK frames later; leaving the
#: lane in that window is a dodge, and staying in it is a hit.
AIM_PROBE = """
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
const press = { key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} };
keyHandlers.forEach(fn => fn(press));
run(2);
/* One volley, dodged: wait for the lock, step off the line, count the
   frames until the shot, and watch it sail past. */
function volley(dodge){
  let guard = 0;
  while (e.aim < 0 && guard++ < 3000) run(1);
  if (e.aim < 0) return null;
  const aimed = e.aim;
  if (dodge) { p.lane = (aimed + 1) % 3 } else { p.lane = aimed }
  let lockToFire = 0;
  while (e.beam <= 0 && e.aim >= 0 && guard++ < 3000) { run(1); lockToFire++ }
  const beamLane = e.beamLane, hpBefore = p.hp;
  while (e.beam > 0 && guard++ < 3000) run(1);
  return { aimed: aimed, beamLane: beamLane, lockToFire: lockToFire,
    hpBefore: hpBefore, hpAfter: p.hp };
}
const dodged = volley(true);
const stayed = volley(false);
console.log(JSON.stringify({ aimLock: duelFacts().aimLock,
  dodged: dodged, stayed: stayed }));
"""


def aim_probe(script: str) -> str:
    """The page's own script, wrapped so one aimed volley can be watched."""

    return AIM_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The whole match's tempo, measured act by act (§6, C-1318): a perfect
#: dodger takes twelve volleys at full health, at first blood, and at match
#: point, and the frames between shots must shrink while the locked
#: telegraph window stays as long as ever.
PACE_PROBE = """
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
const press = { key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} };
keyHandlers.forEach(fn => fn(press));
run(2);
/* Twelve dodged volleys at one health state: step off the locked lane
   every frame, record the gap between consecutive shots and how long the
   aim stayed locked before each. */
function paceOf(hp, volleys){
  e.hp = hp; p.hp = 3;
  const gaps = [], locks = [];
  let guard = 0, lastFire = null, frame = 0, lockAt = null;
  let fired = 0, wasBeam = false, wasAim = false, chargeRate = 0;
  while (fired < volleys && guard++ < 30000) {
    if (e.aim >= 0 && p.lane === e.aim) { p.lane = (e.aim + 1) % 3 }
    const c0 = e.charge;
    run(1); frame++;
    /* The foe's fill rate, read off a single frame of holding: this is
       the deterministic half of the act's tempo, free of the volley
       timing's seeded noise. */
    if (e.charge > c0) { chargeRate = Math.max(chargeRate, e.charge - c0) }
    if (e.aim >= 0 && !wasAim) { lockAt = frame }
    wasAim = e.aim >= 0;
    const isBeam = e.beam > 0;
    if (isBeam && !wasBeam) {
      if (lastFire !== null) gaps.push(frame - lastFire);
      if (lockAt !== null) locks.push(frame - lockAt);
      lastFire = frame; lockAt = null; fired++;
    }
    wasBeam = isBeam;
  }
  const mean = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length : null;
  return { act: duelFacts().act, mean: mean, n: gaps.length, rate: chargeRate,
    scene: SCENE,
    minLock: locks.length ? Math.min.apply(null, locks) : null };
}
const opening = paceOf(3, 12);
const middle = paceOf(2, 12);
const clutch = paceOf(1, 12);
console.log(JSON.stringify({ style: duelFacts().style, tense: duelFacts().tense,
  opening: opening, middle: middle, clutch: clutch,
  scenes: sceneFacts().scenes,
  hud: hudFacts(),
  state: state, pHp: p.hp }));
"""


#: Machine-gun fire at match-point tempo, watching the full-screen flash
#: overlay: the worst one-second window must hold at most three onsets
#: (§15, WCAG 2.3.1), while the flash itself stays alive.
FLASH_PROBE = """
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
function down(){ (handlers.keydown||[]).forEach(fn => fn({ key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} })) }
function up(){ (handlers.keyup||[]).forEach(fn => fn({ key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} })) }
down(); up();
run(5);
/* Match point, the fastest act; the player machine-guns minimum charges
   and both fighters' pools are pinned so the barrage never ends early. */
e.hp = 1;
let prev = 0, onsets = [], frame = 0;
for (let i = 0; i < 900; i++) {
  if (i % 20 < 14) { down() } else if (i % 20 === 14) { up() }
  p.hp = 3;
  run(1); frame++;
  if (flash > prev + 0.5) onsets.push(frame);
  prev = flash;
}
let worst = 0;
for (const t of onsets) { const w = onsets.filter(x => x > t - 60 && x <= t).length; if (w > worst) worst = w }
console.log(JSON.stringify({ onsets: onsets.length, frames: frame,
  worstWindow: worst, state: state }));
"""


def flash_probe(script: str) -> str:
    """The page's own script, wrapped so the strobe rate can be counted."""

    return FLASH_PROBE.replace("SCRIPT_PLACEHOLDER", script)


def pace_probe(script: str) -> str:
    """The page's own script, wrapped so the match's tempo can be timed."""

    return PACE_PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = [
    "DUEL_DIFFICULTY",
    "DUEL_HOW",
    "DUEL_SCRIPT",
    "DUEL_TITLE",
    "DUEL_WORDS",
    "AIM_PROBE",
    "PACE_PROBE",
    "pace_probe",
    "FLASH_PROBE",
    "flash_probe",
    "PROBE",
    "aim_probe",
    "probe_source",
]
