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
from the audio and juice preambles.
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
    "← → で移動、SPACE で連射。敵の波を落とす。3 回ぶつかると終わり。"
    "R でやり直し、M で消音。"
)

SHOOTER_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const FALL=SPEED_TOKEN,WAVE=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const W=cv.width,H=cv.height,SHIP=22;
let ship,shots,foes,stars,score,wave,t,state,fire;
function reset(){ship={x:W/2,y:H-34,hp:3,cool:0};shots=[];foes=[];score=0;wave=0;
  t=0;state='play';fire=false;rs=(SEED>>>0)||1;
  stars=[];for(let i=0;i<48;i++){stars.push({x:rand()*W,y:rand()*H,s:0.4+rand()*1.4})}}
/* A formation, not a scatter: rows read as a wave the player can answer. */
function spawn(){wave++;const n=3+Math.floor(rand()*4),gap=W/(n+1),
  drop=0.35+rand()*0.35,sway=rand()<0.5?-1:1;
  for(let i=0;i<n;i++){foes.push({x:gap*(i+1),y:-24-((i%2)*18),
    vy:FALL*(0.8+drop),vx:sway*(0.2+rand()*0.5),r:13,hp:1})}}
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
  shots.push({x:ship.x,y:ship.y-16});sfx('fire')}
function step(){const now=performance.now();
  combat(state==='play'&&gateState()==='playing');
  if(state==='play'){t++;
    if(ship.cool>0)ship.cool--;
    if(keys['arrowleft']||keys['a']){ship.x=Math.max(SHIP,ship.x-4)}
    if(keys['arrowright']||keys['d']){ship.x=Math.min(W-SHIP,ship.x+4)}
    if(fire)shoot();
    if(t%Math.round(WAVE)===0)spawn();
    shots.forEach(s=>{s.y-=7});
    shots=shots.filter(s=>s.y>-10);
    foes.forEach(f=>{f.y+=f.vy;f.x+=f.vx;
      if(f.x<f.r||f.x>W-f.r){f.vx*=-1}});
    /* Hits first, then the ship: a foe that reaches the ship and is shot on
       the same frame should not both kill and die. */
    shots.forEach(s=>{foes.forEach(f=>{
      if(f.hp>0&&Math.hypot(f.x-s.x,f.y-s.y)<f.r+4){
        f.hp=0;s.y=-99;score++;sfx('hurt');shake(4);burst(f.x,f.y,12,'ACCENT_JUICE')}})});
    foes.forEach(f=>{if(f.hp>0&&Math.hypot(f.x-ship.x,f.y-ship.y)<f.r+SHIP*0.6){
      f.hp=0;ship.hp--;sfx('clash');shake(11);hitstop(5);
      burst(ship.x,ship.y,18,'ALERT_JUICE');
      if(ship.hp<=0){state='over';failBeat(ship.x,ship.y)}}});
    foes=foes.filter(f=>f.hp>0&&f.y<H+30);
    shots=shots.filter(s=>s.y>-10);
    stars.forEach(s=>{s.y+=REDUCED?0:s.s;if(s.y>H){s.y=0;s.x=rand()*W}})}
  draw(now);requestAnimationFrame(step)}
function draw(now){
  cx.fillStyle='SURFACE_TOKEN';cx.fillRect(0,0,W,H);
  cx.fillStyle='#ffffff44';
  stars.forEach(s=>{cx.fillRect(s.x,s.y,s.s,s.s*2)});
  cx.fillStyle='CYAN_TOKEN';
  shots.forEach(s=>{cx.fillRect(s.x-1.5,s.y-8,3,10)});
  /* Foes read by shape as well as colour (C-1018): a hull with a notch. */
  foes.forEach(f=>{sprite('foe',f.x-f.r,f.y-f.r,f.r*2,f.r*2,'');
    cx.fillStyle='MAGENTA_TOKEN';cx.beginPath();
    cx.moveTo(f.x,f.y+f.r);cx.lineTo(f.x-f.r,f.y-f.r*0.6);
    cx.lineTo(f.x,f.y-f.r*0.1);cx.lineTo(f.x+f.r,f.y-f.r*0.6);
    cx.closePath();cx.fill()});
  const flick=FRAME(3,14,now);
  cx.fillStyle='RAISED_TOKEN';
  cx.beginPath();cx.moveTo(ship.x,ship.y-SHIP);
  cx.lineTo(ship.x-SHIP*0.8,ship.y+SHIP*0.7);
  cx.lineTo(ship.x+SHIP*0.8,ship.y+SHIP*0.7);cx.closePath();cx.fill();
  cx.fillStyle='CYAN_TOKEN';
  cx.fillRect(ship.x-3,ship.y+SHIP*0.7,6,6+flick*3);
  cx.fillStyle='MAGENTA_TOKEN';
  for(let i=0;i<ship.hp;i++){cx.fillRect(12+i*18,10,14,10)}
  cx.fillStyle='#dfe7f5';cx.font='13px ui-monospace,monospace';
  cx.fillText('撃墜 '+score+'  第 '+wave+' 波',W-170,19);
  if(state==='over'){cx.fillStyle='#05070fd0';cx.fillRect(0,0,W,H);
    cx.fillStyle='#dfe7f5';cx.font='20px ui-monospace,monospace';
    const a='撃墜 '+score+' 機。';cx.fillText(a,W/2-a.length*10,H/2-8);
    cx.font='13px ui-monospace,monospace';
    const b='SPACE か R、タップでもう一度';cx.fillText(b,W/2-b.length*6.5,H/2+18)}}
reset();step();
"""

__all__ = [
    "SHOOTER_DIFFICULTY",
    "SHOOTER_HOW",
    "SHOOTER_SCRIPT",
    "SHOOTER_TITLE",
    "SHOOTER_WORDS",
]
