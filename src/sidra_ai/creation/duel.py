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
let p,e,state,winner,flash,spark,mash;
function fighter(x){return {x:x,lane:1,hp:3,charge:0,beam:0,beamLane:1,hold:false,
  think:0,hitLock:false,over:0,stun:0}}
function duelFacts(){return {style:CPU_STYLE,fire:CPU_FIRE,overLimit:OVER_LIMIT,
  playerStun:p?p.stun:0,playerOver:p?p.over:0,enemyStun:e?e.stun:0}}
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
  if(f.charge>18){f.beam=f.charge;f.beamLane=f.lane;flash=1;sfx('fire');
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
  if(e.think<=0){e.think=(CTHINK+rand()*CTHINK)*CPU_THINK;
    const move=rand();
    if(move<0.45){e.lane=p.lane}
    else if(move<0.7){e.lane=Math.floor(rand()*3)}
    if(e.beam<=0){e.hold=true}}
  if(e.hold){e.charge+=0.9*CSPEED;
    /* Same rule, same fighter: an opponent immune to the overload would be
       a penalty on the player rather than a rule of the game. */
    if(e.charge>=100){e.over++;if(e.over>OVER_LIMIT){overload(e);return}}
    if(e.charge>CPU_FIRE[0]+rand()*CPU_FIRE[1]){e.hold=false;e.over=0;
      if(rand()<0.6){e.lane=p.lane}
      e.beam=e.charge;e.beamLane=e.lane;
      e.hitLock=(p.lane===e.beamLane);
      e.charge=0;flash=1;sfx('fire')}}}
function hit(who){who.hp--;flash=1;sfx('hurt');
  shake(10);hitstop(5);burst(who.x,LANES[who.lane],18,'ALERT_JUICE');
  if(who.hp<=0){state='end';
    if(who===e){winner='勝利。ひかりが押し切った。';sfx('win')}
    else{winner='敗北。もう一度。';failBeat(PX,LANES[p.lane])}}}
function step(){const now=performance.now();
  combat(state==='play'&&gateState()==='playing');
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
  cx.fillStyle='SURFACE_TOKEN';cx.fillRect(0,0,cv.width,cv.height);
  cx.fillStyle='RAISED_TOKEN';cx.fillRect(0,cv.height-24,cv.width,24);
  if(flash>0){cx.globalAlpha=0.5*ease(flash);cx.fillStyle='#f5f7ff';
    cx.fillRect(0,0,cv.width,cv.height);cx.globalAlpha=1;flash-=0.05}
  aura(PX,LANES[p.lane],26+p.charge*0.2,'CYAN_TOKEN',now);
  aura(EX,LANES[e.lane],26+e.charge*0.2,'MAGENTA_TOKEN',now);
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
  cx.fillStyle='#9fb0c8';cx.font='12px ui-monospace,monospace';
  cx.fillText('相手: '+(CPU_STYLE==='quick'?'早撃ち型':'溜め型'),cv.width/2-40,20)
  cx.fillStyle='#dfe7f5';cx.font='13px ui-monospace,monospace';
  if(p.beam>0&&e.beam>0&&p.beamLane===e.beamLane){
    cx.fillStyle='#dfe7f5';
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
  if(state==='end'){cx.fillStyle='#05070fd0';cx.fillRect(0,0,cv.width,cv.height);
    cx.fillStyle='#dfe7f5';cx.font='20px ui-monospace,monospace';
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


__all__ = [
    "DUEL_DIFFICULTY",
    "DUEL_HOW",
    "DUEL_SCRIPT",
    "DUEL_TITLE",
    "DUEL_WORDS",
    "PROBE",
    "probe_source",
]
