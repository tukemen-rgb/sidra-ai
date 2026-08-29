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
let p,e,state,winner,flash,spark,mash;
function fighter(x){return {x:x,lane:1,hp:3,charge:0,beam:0,beamLane:1,hold:false,think:0}}
function reset(){p=fighter(PX);e=fighter(EX);state='play';winner='';flash=0;spark=0;mash=0;
  rs=(SEED>>>0)||1}
addEventListener('keydown',ev=>{
  if(ev.code==='Space'){ev.preventDefault();
    if(state!=='play'){reset();return}
    if(p.beam>0&&e.beam>0){mash+=3;sfx('clash')}else{if(!p.hold){sfx('charge')}p.hold=true}}
  if(ev.key==='ArrowUp'&&p.lane>0){p.lane--}
  if(ev.key==='ArrowDown'&&p.lane<2){p.lane++}
  if(ev.key==='r'||ev.key==='R'){reset()}});
addEventListener('keyup',ev=>{if(ev.code==='Space'){fire(p)}});
cv.addEventListener('pointerdown',()=>{if(state!=='play'){reset();return}
  if(p.beam>0&&e.beam>0){mash+=3;sfx('clash')}else{if(!p.hold){sfx('charge')}p.hold=true}});
cv.addEventListener('pointerup',()=>{fire(p)});
function fire(f){if(state!=='play'||!f.hold)return;f.hold=false;
  if(f.charge>18){f.beam=f.charge;f.beamLane=f.lane;flash=1;sfx('fire');
    /* the kick scales with the charge: a tap fires a thread, a long hold
       fires something that shoves the camera */
    shake(2+f.charge*0.08);burst(f.x,LANES[f.lane],10,'ACCENT_JUICE')}
  f.charge=0}
function cpu(){e.think--;
  if(e.think<=0){e.think=CTHINK+rand()*CTHINK;
    const move=rand();
    if(move<0.45){e.lane=p.lane}
    else if(move<0.7){e.lane=Math.floor(rand()*3)}
    if(e.beam<=0){e.hold=true}}
  if(e.hold){e.charge+=0.9*CSPEED;
    if(e.charge>40+rand()*55){e.hold=false;e.beam=e.charge;e.beamLane=e.lane;
      e.charge=0;flash=1}}}
function hit(who){who.hp--;flash=1;sfx('hurt');
  shake(10);hitstop(5);burst(who.x,LANES[who.lane],18,'ALERT_JUICE');
  if(who.hp<=0){state='end';
    if(who===e){winner='勝利。ひかりが押し切った。';sfx('win')}
    else{winner='敗北。もう一度。';sfx('lose')}}}
function step(){const now=performance.now();
  if(state==='play'){
    if(p.hold){p.charge=Math.min(100,p.charge+1.4)}
    cpu();
    const pB=p.beam>0,eB=e.beam>0,same=p.beamLane===e.beamLane;
    if(pB&&eB&&same){
      /* the clash: mashing feeds the player side, charge fed the CPU side */
      spark+=(mash*0.8+p.beam*0.02)-(e.beam*0.045*CSPEED);mash=Math.max(0,mash-1);
      if(spark>60){hit(e);p.beam=0;e.beam=0;spark=0}
      if(spark<-60){hit(p);p.beam=0;e.beam=0;spark=0}}
    else{
      if(pB){p.beam-=2;if(p.beam<=0){if(e.lane===p.beamLane){hit(e)}p.beam=0}}
      if(eB){e.beam-=2;if(e.beam<=0){if(p.lane===e.beamLane){hit(p)}e.beam=0}}}}
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
  const mid=clash?(cv.width/2+spark*3):(dir>0?cv.width:0);
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
  if(p.charge>0){cx.fillStyle='RAISED_TOKEN';cx.fillRect(16,26,104,8);
    cx.fillStyle='CYAN_TOKEN';cx.fillRect(18,28,p.charge,4)}
  cx.fillStyle='#dfe7f5';cx.font='13px ui-monospace,monospace';
  if(p.beam>0&&e.beam>0&&p.beamLane===e.beamLane){
    cx.fillText('押し合い。SPACE 連打で押し返す。',cv.width/2-110,44)}
  if(state==='end'){cx.fillStyle='#05070fd0';cx.fillRect(0,0,cv.width,cv.height);
    cx.fillStyle='#dfe7f5';cx.font='20px ui-monospace,monospace';
    cx.fillText(winner,cv.width/2-winner.length*10,cv.height/2-6);
    cx.font='13px ui-monospace,monospace';
    cx.fillText('SPACE / タップでもう一度',cv.width/2-78,cv.height/2+20)}}
reset();step();
"""

__all__ = [
    "DUEL_DIFFICULTY",
    "DUEL_HOW",
    "DUEL_SCRIPT",
    "DUEL_TITLE",
    "DUEL_WORDS",
]
