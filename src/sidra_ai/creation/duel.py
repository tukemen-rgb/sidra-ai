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

import json

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
/* The far layer (§7 観察 7, C-1345): distance is drawn by CONTRAST - a
   skyline in the midground's own paint, faded toward the sky, behind the
   two fighters. A fixed function of x (no rand(): the arena every seed
   promised does not move), never animated. Same contract as the kaiju's:
   draw() paints through FAR_A and depthFacts() reports the paints. */
const FAR_A=0.22;
function depthFacts(){const keep=SCENE,out=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;
    out.push({sky:scenePaint('SURFACE_TOKEN'),solid:scenePaint('BORDER_TOKEN'),
      alpha:FAR_A})}
  SCENE=keep;return out}
function duelAct(){if(!p||!e)return 0;
  const low=Math.min(p.hp,e.hp);
  return low<=1?2:(p.hp<3||e.hp<3)?1:0}
function tempo(){return TENSE[duelAct()]}
let p,e,state,winner,flash,spark,mash;
/* The two ways a heart is lost, counted apart (C-1422). They are different
   mistakes: a beam that lands was fired into the lane the player was
   standing in, and a lost clash was a shove that did not push hard enough.
   Counting only - the damage and the CPU are untouched by these lines. */
let lostBeam,lostClash;
function fighter(x){return {x:x,lane:1,hp:3,charge:0,beam:0,beamLane:1,hold:false,
  think:0,hitLock:false,over:0,stun:0,aim:-1,fireAt:0,sq:1,hurt:0,smoke:0}}
/* A blow reads in three beats (§6 観察 2, C-1377): flash, smoke that
   stays, the silhouette back out of it - the kaiju leg's numbers
   (C-1032) and the guardian's (C-1343), now on both duelists. The
   third boss grammar was built on stayed one beat short. */
function beatTick(f){if(f.hurt>0)f.hurt--;if(f.smoke>0)f.smoke--}
function beatFacts(){return {p:{hurt:p.hurt,smoke:p.smoke},
  e:{hurt:e.hurt,smoke:e.smoke}}}
/* Squash & stretch for the fighters (§1, C-1358): the jump got it in
   C-1332 and the basket in C-1341, and the duel - whose whole loop is
   the exchange of impacts - stayed rigid. Three verbs write it: holding
   a charge sinks the body in proportion (anticipation), a released shot
   snaps it tall, a landed hit crushes it. Every frame walks a quarter
   step back to its pose and snaps inside 0.01 (C-1332's recipe). Under
   reduced motion nothing ever writes it and the silhouette never moves. */
function poseOf(f){return f.hold?1-Math.min(0.15,f.charge*0.0015):1}
function settleSq(f){if(REDUCED){f.sq=1;return}
  const w=poseOf(f);f.sq+=(w-f.sq)*0.25;if(Math.abs(f.sq-w)<0.01){f.sq=w}}
function squashFacts(){return {p:p?p.sq:1,e:e?e.sq:1}}
/* The face, as a fact (§1, C-1355): which way the player's eyes lean -
   at the enemy's lane, +1 down / -1 up / 0 level - and whether this
   frame is the blink. Under reduced motion FRAME pins the eyes open. */
function faceFacts(){return {look:e.lane>p.lane?1:e.lane<p.lane?-1:0,
  blink:FRAME(40,6,performance.now())===1}}
function duelFacts(){return {style:CPU_STYLE,fire:CPU_FIRE,overLimit:OVER_LIMIT,latch:LATCH,
  act:duelAct(),tense:TENSE.slice(),
  playerStun:p?p.stun:0,playerOver:p?p.over:0,enemyStun:e?e.stun:0,
  aim:e?e.aim:-1,aimLock:AIM_LOCK,enemyHold:e?e.hold:false,
  enemyCharge:e?e.charge:0,enemyFireAt:e?e.fireAt:0,
  enemyBeam:e?e.beam:0,enemyBeamLane:e?e.beamLane:-1,
  pLane:p?p.lane:-1,pHp:p?p.hp:0,eHp:e?e.hp:0,
  lostBeam:lostBeam||0,lostClash:lostClash||0}}
function overload(f){f.stun=STUN_FRAMES;f.hold=false;f.charge=0;f.over=0;
  if(!REDUCED){f.sq=0.7}
  /* heard at the fighter it happens to (§2 増築, C-1398) */
  sfx('hurt',1,f.x/cv.width);shake(9);hitstop(4);burst(f.x,LANES[f.lane],16,'ALERT_JUICE')}
function reset(){p=fighter(PX);e=fighter(EX);state='play';winner='';flash=0;spark=0;mash=0;
  lostBeam=0;lostClash=0;
  rs=(SEED>>>0)||1}
/* Holding is the authored feel, and for some hands it is the whole wall
   (§29, C-1662): GAG's motor guidelines ask that a button held down never
   be the only way. LATCH turns the same one button into press-to-charge
   and press-again-to-fire, so the charge can be taken at any length
   without a finger staying down. Off by default; the panel owns it. */
let LATCH=false;try{LATCH=tuneFlag('latch',false)}catch(err){}
function pressCharge(){
  if(state!=='play'){reset();return}
  if(p.stun>0)return;
  if(p.beam>0&&e.beam>0){mash+=3;sfx('clash');return}
  /* Latched and already charging: this press is the release. */
  if(LATCH&&p.hold){fire(p);return}
  if(!p.hold){sfx('charge')}
  p.hold=true}
addEventListener('keydown',ev=>{
  if(ev.code==='Space'){ev.preventDefault();pressCharge()}
  if(p.stun<=0&&ev.key==='ArrowUp'&&p.lane>0){p.lane--}
  if(p.stun<=0&&ev.key==='ArrowDown'&&p.lane<2){p.lane++}
  if(ev.key==='r'||ev.key==='R'){reset()}});
addEventListener('keyup',ev=>{if(ev.code==='Space'&&!LATCH){fire(p)}});
cv.addEventListener('pointerdown',()=>{pressCharge()});
cv.addEventListener('pointerup',()=>{if(!LATCH){fire(p)}});
function fire(f){if(state!=='play'||!f.hold||f.stun>0)return;f.hold=false;f.over=0;
  if(f.charge>18){f.beam=f.charge;f.beamLane=f.lane;if(flashGate())flash=1;sfx('fire');
    /* the release: the sunken pose snaps tall for one beat (§1, C-1358) */
    if(!REDUCED){f.sq=1.25}
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
function hit(who){who.hp--;if(flashGate())flash=1;
  /* WHO got hit is a left-or-right fact - the ear learns it too (§2
     増築, C-1398): the struck fighter's own x, the same one the burst
     and the knock already use. */
  sfx('hurt',1,who.x/cv.width);
  who.hurt=8;who.smoke=34;
  if(!REDUCED){who.sq=0.7}
  shake(10);hitstop(5);burst(who.x,LANES[who.lane],18,'ALERT_JUICE');
  if(who.hp<=0){state='end';
    if(who===e){winner='勝利。ひかりが押し切った。';winBeat(EX,LANES[e.lane])}
    /* The verdict only (§6 観察 8, C-1637): the invitation is the
       gated line below, which waits out the quiet. This one used to say
       「もう一度」 itself, so the ask arrived on the ending's first frame
       while every other template held it. */
    else{winner='敗北。ひかりが押し切られた。';failBeat(PX,LANES[p.lane])}}}
function step(rt){const now=performance.now();
  /* The world advances on real time, not on this display's refresh
     rate (§26, C-1608 — the gate C-1607 built and racing proved).
     Drawing is NOT gated: a 120Hz screen still gets 120 pictures a
     second, the world just stops happening twice as fast. */
  if(!TICK(rt)){draw(now);return requestAnimationFrame(step)}
  worldStep();
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
      if(spark<-60){lostClash++;hit(p);p.beam=0;e.beam=0;spark=0}}
    else{
      if(pB){p.beam-=2;if(p.beam<=0){if(p.hitLock){hit(e)}p.beam=0;p.hitLock=false}}
      if(eB){e.beam-=2;if(e.beam<=0){if(e.hitLock){lostBeam++;hit(p)}e.beam=0;e.hitLock=false}}}}
  /* outside the play-guard so a knocked-out loser still settles upright */
  settleSq(p);settleSq(e);
  beatTick(p);beatTick(e);
  draw(now);requestAnimationFrame(step)}
function aura(x,y,r,c,now){const s=REDUCED?0:FRAME(4,6,now);
  cx.globalAlpha=0.25;cx.fillStyle=c;
  cx.beginPath();cx.arc(x,y,r+s*2,0,6.28318);cx.fill();cx.globalAlpha=1}
function body(x,y,c,mir,face,sq){
  /* The deformation is one transform, feet-anchored: heights shrink by
     sq, widths grow by (2-sq) so the volume reads constant (C-1332's
     drawing rule). At sq=1 every coordinate is bit-identical to the
     rigid body, which is what the reduced-motion run promises. */
  sq=sq||1;const bt=y+18,wd=2-sq;
  function part(rx,ry,rw,rh){cx.fillRect(x+(rx-x)*wd,bt+(ry-bt)*sq,rw*wd,rh*sq)}
  sprite('fighter',x+(-12)*wd,bt+(y-26-bt)*sq,24*wd,44*sq,'');
  cx.fillStyle=c;part(x-9,y-24,18,20);
  part(x-6,y-4,12,22);
  cx.fillStyle='#05070f';
  /* The enemy keeps its flat visor; the player's face is the fourth in
     the contract (§1, C-1355): two eyes that lean toward the enemy's
     LANE - the whole game is three lanes, and the fighter watching them
     is the mind-game made visible. The blink is one FRAME beat, pinned
     open under reduced motion (C-1348's rule, verbatim). */
  if(!face){part(x-9+(mir?10:2),y-20,6,5);return}
  if(face.blink)return;
  const ey=face.look*1.5,ex=x-9+(mir?10:2);
  part(ex,y-20+ey,2.5,3);part(ex+3.5,y-20+ey,2.5,3)}
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
  /* The ruined skyline, one haze-step off the sky (観察 7). */
  cx.globalAlpha=FAR_A;cx.fillStyle=scenePaint('BORDER_TOKEN');
  for(let fx=0;fx<cv.width;fx+=48){
    const fh=20+18*Math.abs(Math.sin(fx*0.11+5));
    cx.fillRect(fx,cv.height-24-fh,34,fh)}
  cx.globalAlpha=1;
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
  /* Beat one: the blow turns the body white for eight frames - the same
     state paint as the kaiju leg's, not a strobe (§6 観察 2, C-1377). */
  body(PX,LANES[p.lane],p.hurt>0?'#dfe7f5':'CYAN_TOKEN',true,faceFacts(),p.sq);
  body(EX,LANES[e.lane],e.hurt>0?'#dfe7f5':'MAGENTA_TOKEN',false,undefined,e.sq);
  /* Beat two: smoke that outlives the flash, fading where the hit
     landed; beat three is the body already drawn, re-emerging as it
     thins. Same 34-frame envelope as the other two bosses. */
  [[p,PX],[e,EX]].forEach(pair=>{const f=pair[0];
    if(f.smoke>0){cx.fillStyle='#dfe7f5';cx.globalAlpha=f.smoke/70;
      cx.beginPath();cx.arc(pair[1],LANES[f.lane],24,0,6.283);cx.fill();
      cx.globalAlpha=1}});
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
  cx.fillStyle=HUD_INK;cx.font='13px ui-monospace,monospace';
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
    if((typeof roundAskReady!=='function'||roundAskReady())){cx.fillText('SPACE / タップでもう一度',cv.width/2-78,cv.height/2+20)}}}
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



#: The two weights this page uses (§1, C-1652): over-charging your own
#: beam until it backfires kicks the camera by 9, taking a hit kicks it by
#: 10 - a mistake you made costs less than a blow you were dealt. Both
#: ring the same sound, so they are told apart by what the page's own
#: state did: an overload stuns, a hit costs a heart.
LADDER_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
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
PROBE_EARS_PLACEHOLDER
SCRIPT_PLACEHOLDER
PROBE_SEND_PLACEHOLDER
PROBE_EYES_PLACEHOLDER
PROBE_SHAKE_PLACEHOLDER
/* Only a frame that rang this event and nothing else can attribute the
   kick to it (C-1652): the combo step-up in combo.py kicks by 3, and
   shake() keeps the max within a frame as well as across them. */
let rang = [];
const realSfx = sfx;
sfx = function(name){ rang.push(String(name)); return realSfx.apply(this, arguments) };
function alone(name){ return rang.length === 1 && rang[0] === name }
function frame(){ rang = [];
  eeTick();
  return probeKick(() => { if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }) }
probeSend('keydown', ' ', handlers); probeSend('keyup', ' ', handlers);
frame(); frame();
function settle(n){ for (let i = 0; i < (n || 120); i++) { frame() } }

/* --- the light one: hold the charge until it backfires --- */
let over = null;
p.stun = 0; p.hold = true; p.charge = 100; p.over = OVER_LIMIT - 1;
for (let i = 0; i < 60 && over === null; i++) {
  const stunBefore = p.stun;
  const kick = frame();
  if (p.stun > stunBefore && alone('hurt')) { over = { kick: kick, stun: p.stun } }
  if (p.hold === false && p.stun === 0) { p.hold = true; p.charge = 100; p.over = OVER_LIMIT - 1 }
}
settle();

/* --- the heavy one: stand in the line of fire and take the beam. The
   CPU charges and fires on its own schedule; standing in its aim is all
   a loss needs, which is how the loss probe drives this same page. --- */
let struck = null;
for (let i = 0; i < 4000 && struck === null; i++) {
  const hpBefore = p.hp;
  if (e.aim >= 0) { p.lane = e.aim }
  const kick = frame();
  if (p.hp < hpBefore && alone('hurt')) { struck = { kick: kick, hp: p.hp } }
  if (state !== 'play') break;
}
const pair = earEye('hurt', cv.width);
console.log(JSON.stringify({ pair: pair, light: over, heavy: struck }));
"""


def ladder_probe(script: str) -> str:
    """The page's own script, wrapped so both weights can be read."""

    from sidra_ai.creation.probekit import (
        PROBE_EARS,
        PROBE_EYES,
        PROBE_SEND,
        PROBE_SHAKE,
    )

    return (
        LADDER_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("PROBE_SEND_PLACEHOLDER", PROBE_SEND)
        .replace("PROBE_SHAKE_PLACEHOLDER", PROBE_SHAKE)
        .replace("PROBE_EARS_PLACEHOLDER", PROBE_EARS)
        .replace("PROBE_EYES_PLACEHOLDER", PROBE_EYES)
    )



#: The same action at two weights (§1, C-1657). This page's kick is not a
#: rung, it is a slope: `shake(2 + charge*0.08)`, so a tap fires a thread
#: and a long hold shoves the camera. The ladder contract compares
#: different events; nothing asked whether one event scales with what was
#: put into it, and flattening the formula to a constant left 166 tests
#: green.
SLOPE_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
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
PROBE_SEND_PLACEHOLDER
PROBE_SHAKE_PLACEHOLDER
let rang = [];
const realSfx = sfx;
sfx = function(name){ rang.push(String(name)); return realSfx.apply(this, arguments) };
/* Only a frame that rang this one event can attribute the kick to it
   (C-1652): the combo step-up kicks by 3 and shake() keeps the max
   within a frame as well as across them. */
function alone(name){ return rang.length === 1 && rang[0] === name }
function frame(){ rang = [];
  return probeKick(() => { if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }) }
probeSend('keydown', ' ', handlers); probeSend('keyup', ' ', handlers);
frame(); frame();
function settle(n){ for (let i = 0; i < (n || 40); i++) { frame() } }

/* One shot at a named charge, pulled through the page's own fire() - the
   same way the dungeon's probe swings the page's own blade. Reading it
   inside a frame does not work: the trigger is serviced outside the step
   this probe controls, so the accumulator is cleared after the kick
   rather than before it. Cleared here, fired here, read here. */
function shotAt(charge){
  settle();
  rang = [];
  p.stun = 0; p.beam = 0; p.hold = true; p.over = 0; p.charge = charge;
  SHAKE = 0;
  fire(p);
  const kick = shakeAmount();
  if (!alone('fire')) { return null }
  return { charge: charge, kick: kick, beam: p.beam, rang: rang.slice() };
}
const light = shotAt(20);
const heavy = shotAt(100);
console.log(JSON.stringify({ light: light, heavy: heavy }));
"""


def slope_probe(script: str) -> str:
    """The page's own script, wrapped so one action can be weighed twice."""

    from sidra_ai.creation.probekit import PROBE_SEND, PROBE_SHAKE

    return (
        SLOPE_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("PROBE_SEND_PLACEHOLDER", PROBE_SEND)
        .replace("PROBE_SHAKE_PLACEHOLDER", PROBE_SHAKE)
    )



#: Can this page be played without ever holding a button down? (§29,
#: C-1662.) Driven both ways in one probe: with the panel's latch off the
#: authored feel must be intact - taps alone leave the barrel cold - and
#: with it on the same taps must put a real beam out. One direction alone
#: would pass an implementation that latched always, or one that latched
#: never.
LATCH_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.localStorage = { getItem: () => LATCH_INPUT, setItem(){}, removeItem(){} };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
PROBE_SEND_PLACEHOLDER
function frame(){ if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }
/* A TAP: down and up on the same frame, never held across one. */
function tap(){
  probeSend('keydown', ' ', handlers);
  probeSend('keyup', ' ', handlers);
}
frame(); frame();
/* Start the round with a tap, then let the page settle. */
tap(); frame(); frame();
p.stun = 0; p.beam = 0; p.charge = 0; p.hold = false;
/* One tap to begin the charge, frames to let it grow, one tap to let go.
   Nothing is held across a frame boundary at any point. */
tap();
const heldAfterFirstTap = p.hold;
for (let i = 0; i < 40; i++) { frame() }
const chargeBeforeSecond = p.charge;
tap();
const beam = p.beam, chargeAtFire = chargeBeforeSecond;
console.log(JSON.stringify({ latch: duelFacts().latch,
  heldAfterFirstTap: heldAfterFirstTap, charge: chargeAtFire, beam: beam,
  fired: beam > 0 }));
"""


def latch_probe(script: str, *, latch: bool) -> str:
    """The page's own script, driven with taps alone."""

    import json as _json

    from sidra_ai.creation.probekit import PROBE_SEND

    stored = _json.dumps(_json.dumps({"latch": True})) if latch else "null"
    return (
        LATCH_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("PROBE_SEND_PLACEHOLDER", PROBE_SEND)
        .replace("LATCH_INPUT", stored)
    )


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
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn(i * 16); sceneTick() } }
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
console.log(JSON.stringify({
  sceneOrder: sceneOrder, style: duelFacts().style, tense: duelFacts().tense,
  opening: opening, middle: middle, clutch: clutch,
  scenes: sceneFacts().scenes,
  hud: hudFacts(),
  depth: depthFacts(),
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


#: The face, as watched (§1, C-1355): put the enemy in each lane relation
#: on the page's own state, move the player on its own keys, and read
#: where the eyes lean; stand level and count the blink. The clock ticks
#: with the frames (C-1348's lesson: a zero-pinned performance.now
#: freezes the wall-clock FRAME and the blink never comes).
FACE_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
let CLOCK = 0;
globalThis.performance = { now: () => CLOCK };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => rec }) };
/* A recording context, because faceFacts() is a number and a number is
   not paint (C-1618 found this here and fixed one body of six; C-1632 did
   the same for the streak). globalAlpha is tracked across save/restore. */
let ALPHA = 1, RECTS = [];
const STACK = [];
const rec = new Proxy(function(){}, {
  get: (t, k) => {
    if (k === 'globalAlpha') return ALPHA;
    if (k === 'save') return () => { STACK.push(ALPHA) };
    if (k === 'restore') return () => { ALPHA = STACK.length ? STACK.pop() : 1 };
    if (k === 'fillRect') return (x, y, w, h) => { RECTS.push({ x: x, y: y, w: w, h: h }) };
    if (k === Symbol.toPrimitive) return () => 0;
    return nothing },
  set: (t, k, v) => { if (k === 'globalAlpha') { ALPHA = v } return true },
  apply: () => nothing });
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; CLOCK = (F++) * 16; fn(CLOCK) } }
function ev(type, k){
  const e2 = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e2));
}
ev('keydown', ' '); ev('keyup', ' '); run(2);
/* The player walks on its own keys; the enemy's lane is CPU state the
   probe may place (the BEAT_PROBE's licence). */
function lane(want){ while (p.lane > want) { ev('keydown', 'ArrowUp'); run(1) }
  while (p.lane < want) { ev('keydown', 'ArrowDown'); run(1) } }
lane(0); e.lane = 2; run(1);
const below = faceFacts().look;
lane(2); e.lane = 0; run(1);
const above = faceFacts().look;
e.lane = 2; run(1);
const level = faceFacts().look;
/* Then hold the stare and count the blink. */
let blinkFrames = 0, longest = 0, streak = 0;
for (let i = 0; i < 500; i++) { run(1); e.lane = p.lane;
  if (faceFacts().blink) { blinkFrames++; streak++;
    if (streak > longest) longest = streak } else { streak = 0 } }

/* Which painted marks ARE the eyes, without knowing their size in advance
   (C-1634). Two frames that differ only in the blink: the marks the blink
   takes away are the face. Among the small ones, exactly one size occurs
   exactly twice - a left eye and a right eye - and that is the pair. Other
   things can blink on the same beat (the duel's dashed lane line puts 38
   identical squares in this difference), so "exactly twice" is what picks
   the eyes out rather than "small and gone". */
/* Beams off: a beam in flight redraws half the screen between the two
   frames and the difference stops being about the face. */
p.beam = 0; e.beam = 0;
function frameAt(wantBlink){
  for (let i = 0; i < 400; i++) {
    if (!!faceFacts().blink === wantBlink) { RECTS = []; run(1); return RECTS.slice() }
    run(1) }
  return null }
const openFrame = frameAt(false), shutFrame = frameAt(true);
let eyes = 0, eyeSize = null, eyeGap = null;
if (openFrame && shutFrame) {
  const key = r => r.w + 'x' + r.h;
  const left = {};
  for (const r of shutFrame) { left[key(r)] = (left[key(r)] || 0) + 1 }
  const gone = [];
  for (const r of openFrame) {
    const k = key(r);
    if (left[k] > 0) { left[k]-- } else if (r.w > 0 && r.w <= 6 && r.h > 0 && r.h <= 6) { gone.push(r) }
  }
  const bySize = {};
  for (const r of gone) { (bySize[key(r)] = bySize[key(r)] || []).push(r) }
  for (const k of Object.keys(bySize)) {
    if (bySize[k].length === 2) { eyes = 2; eyeSize = k;
      eyeGap = Math.abs(bySize[k][0].x - bySize[k][1].x) } }
}
console.log(JSON.stringify({
  eyes: eyes, eyeSize: eyeSize, eyeGap: eyeGap,
  below: below, above: above, level: level,
  blinkFrames: blinkFrames, longestBlink: longest,
}));
"""


def face_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the fighter's face can be watched."""

    return FACE_PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "SCRIPT_PLACEHOLDER", script
    )


#: The fighter's silhouette under its three impacts (§1, C-1358): hold a
#: real Space until the body sinks (anticipation), release and catch the
#: tall snap, then stand in one aimed volley and watch the crush - each
#: settling back to its pose within half a second. The reduced run reads
#: 1 on every sampled frame. Keys are the template's own; the enemy's aim
#: is dodged by lane during the charge so nothing but the verb under test
#: writes the number.
SQUASH_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
let CLOCK = 0;
globalThis.performance = { now: () => CLOCK };
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
function run(n){ for (let i = 0; i < n && queued; i++) { RECTS = []; const fn = queued; queued = null; CLOCK = (F++) * 16; fn(CLOCK) } }
/* Did the paint follow the number? The rest frame's fills are kept and
   a squashed frame has to contain one of them under the template's own
   one-body transform - width the other way, height with it. Nothing is
   hardcoded: the dimensions come from the page's own rest frame. */
let restFills = [];
function followed(sq){
  if (Math.abs(sq - 1) < 1e-9) return false;
  return restFills.some(r => RECTS.some(n =>
    Math.abs(n.w - r.w * (2 - sq)) < 1e-6 && Math.abs(n.h - r.h * sq) < 1e-6)) }

function ev(type, k){
  const e2 = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e2));
}
ev('keydown', ' '); ev('keyup', ' '); run(2);
/* While a phase is watching one verb, the enemy's volleys are dodged by
   lane (PACE_PROBE's licence) and the pools pinned so no stray hit or
   match end writes the number under test. */
function dodge(){ if (e.aim >= 0 && p.lane === e.aim) { p.lane = (e.aim + 1) % 3 } }
/* Phase 0: nobody is doing anything - the player's body must not breathe.
   Short window, before the first volley can land. */
run(1);
restFills = RECTS.slice();
let idleOff = 0, idleDrawn = 0, chargeDrawn = 0, fireDrawn = 0, hurtDrawn = 0;
for (let i = 0; i < 30; i++) { dodge(); run(1); if (squashFacts().p !== 1) idleOff++;
  if (followed(0.7)) idleDrawn++ }
/* Phase 1: hold the charge and watch the anticipation sink in. */
ev('keydown', ' ');
let chargeDip = 1;
for (let i = 0; i < 45; i++) { dodge(); p.hp = 3; run(1);
  chargeDip = Math.min(chargeDip, squashFacts().p);
  if (squashFacts().p < 0.999 && followed(squashFacts().p)) chargeDrawn++ }
const heldCharge = p.charge;
/* Phase 2: let go - fire() runs in the keyup handler, synchronously. */
ev('keyup', ' ');
const released = squashFacts().p;
let settleFire = null;
for (let i = 0; i < 30; i++) { dodge(); p.hp = 3; run(1) }
settleFire = squashFacts().p;
/* Phase 3: stand in one aimed volley and take the hit. */
let guard = 0;
while (e.aim < 0 && guard++ < 3000) { p.hp = 3; run(1) }
if (e.aim >= 0) { p.lane = e.aim }
const hpBefore = p.hp;
let hitSq = null;
while (guard++ < 3000) { run(1);
  if (p.hp < hpBefore) { hitSq = squashFacts().p; break } }
let settleHit = null;
for (let i = 0; i < 30; i++) { p.hp = 3; run(1) }
settleHit = squashFacts().p;
console.log(JSON.stringify({
  idleDrawn: idleDrawn, chargeDrawn: chargeDrawn,
  restFills: restFills.length,
  idleOff: idleOff, chargeDip: chargeDip, heldCharge: heldCharge,
  released: released, settleFire: settleFire,
  gotHit: hitSq !== null, hitSq: hitSq, settleHit: settleHit,
  enemySq: squashFacts().e,
}));
"""


def squash_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the fighters' bounce can be watched."""

    return SQUASH_PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "SCRIPT_PLACEHOLDER", script
    )


#: The blow, heard on the side it landed (§2 増築, C-1398): the real
#: volley drive from BEAT_PROBE - the player's beam onto the stunned CPU,
#: then the CPU's own volley onto the standing player - and each hit's
#: recorded pan must match the struck fighter's x through (x/W*2-1)*0.8,
#: while fire/charge/clash and every other positionless sound builds no
#: panner at all.
PAN_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const keyHandlers = [];
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
const before = pans.length;
/* The player's volley onto the stunned CPU (BEAT_PROBE's drive). */
p.hold = true; run(40);
e.stun = 400; e.lane = p.lane; e.hold = false; e.beam = 0;
fire(p);
let guard = 0;
while (e.hp === 3 && guard++ < 120) run(1);
const eHitPans = pans.slice();
/* Then the CPU's own volley on the standing player. */
e.stun = 0;
guard = 0;
while (p.hp === 3 && guard++ < 2000) run(1);
console.log(JSON.stringify({ before: before, eHp: e.hp, pHp: p.hp,
  pans: pans,
  expected: [(e.x / cv.width * 2 - 1) * 0.8, (p.x / cv.width * 2 - 1) * 0.8] }));
"""


def pan_probe(script: str) -> str:
    """The page's own script, wrapped so each blow's stereo side can be
    read off the audio graph."""

    return PAN_PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = [
    "PAN_PROBE",
    "pan_probe",
    "DUEL_DIFFICULTY",
    "DUEL_HOW",
    "DUEL_SCRIPT",
    "DUEL_TITLE",
    "DUEL_WORDS",
    "AIM_PROBE",
    "BEAT_PROBE",
    "beat_probe_source",
    "FACE_PROBE",
    "face_probe",
    "SQUASH_PROBE",
    "squash_probe",
    "PACE_PROBE",
    "pace_probe",
    "FLASH_PROBE",
    "flash_probe",
    "PROBE",
    "aim_probe",
    "probe_source",
]


#: Fights the real duel two ways, so both of the ways a heart is lost are
#: read off a page that played rather than assumed from the source.
#:
#: ``mode``: ``beam`` stands still and is shot - which is what an untouched
#: go already does - and ``clash`` deliberately walks into the enemy's lane
#: with a barely-charged beam, which is the shove that does not push hard
#: enough. Both are driven through the keys the template listens for, so
#: neither can reach a state a person could not.
LOSS_PROBE = """
const dNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : dNothing),
  apply: () => dNothing, set: () => true });
const dHandlers = {};
globalThis.matchMedia = () => ({ matches: false, addEventListener(){}, addListener(){} });
let dClock = 0;
globalThis.performance = { now: () => dClock };
globalThis.addEventListener = (type, fn) => { (dHandlers[type] = dHandlers[type] || []).push(fn) };
globalThis.Image = function(){ return dNothing };
const dStore = {};
globalThis.localStorage = { getItem: (k) => (k in dStore ? dStore[k] : null),
  setItem: (k, v) => { dStore[k] = String(v) }, removeItem: (k) => { delete dStore[k] } };
globalThis.location = { reload: () => {} };
globalThis.KeyboardEvent = function(type, init){ return Object.assign({ type: type }, init) };
globalThis.dispatchEvent = (ev) => { (dHandlers[ev.type] || []).forEach(fn => fn(ev)); return true };
let dPaint = [];
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => dNothing, querySelector: () => null,
  getElementById: () => ({ width: 720, height: 320, style: {}, addEventListener: () => {},
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => new Proxy({
      fillText: (s) => { dPaint.push(String(s)) }, fillRect: () => {} }, {
      get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : dNothing)),
      set: () => true }) }) };
let dQueued = null;
globalThis.requestAnimationFrame = (fn) => { dQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
const MODE = MODE_INPUT;
let dFrame = 0;
function dKey(type, key, code){ (dHandlers[type] || []).forEach(fn => fn({
  key: key, code: code || key, preventDefault(){}, stopImmediatePropagation(){} })) }
function dStep(){ if (!dQueued) return false;
  const fn = dQueued; dQueued = null; dPaint = []; dClock += 50 / 3; fn(dClock); return true }
dKey('keydown', ' ', 'Space'); dKey('keyup', ' ', 'Space');
dStep(); dStep();
/* Walk to a lane by pressing the same arrow the player would. */
function dGoTo(lane){ for (let i = 0; i < 3 && p.lane !== lane; i++) {
  dKey('keydown', p.lane > lane ? 'ArrowUp' : 'ArrowDown') } }
let charging = false;
for (let f = 0; f < FRAMES_INPUT; f++) {
  if ((MODE === 'clash' || MODE === 'mixed') && state === 'play') {
    if (e.beam > 0 && p.beam <= 0) {
      /* The enemy's beam is in the air. Step into its lane and answer it
         with the least charge that will fire at all - which is exactly the
         shove that loses. */
      dGoTo(e.beamLane);
      if (!charging) { dKey('keydown', ' ', 'Space'); charging = true }
      else if (p.charge > 20) { dKey('keyup', ' ', 'Space'); charging = false }
    } else {
      if (charging && p.charge > 60) {
        /* Never let the charge run away into an overload. */
        dKey('keyup', ' ', 'Space'); charging = false }
      /* Between clashes, get out of the lane the enemy is locking on to.
         Without this the run eats more beams than clashes, and a judge
         that only ever saw the first-listed cause win could not tell
         「the largest」 from 「the first」. */
      if (MODE === 'clash' && e.aim >= 0 && p.lane === e.aim) {
        dGoTo(e.aim === 0 ? 1 : e.aim - 1) } }
  }
  if (!dStep()) break;
  if (state !== 'play') break;
}
const facts = duelFacts();
/* The same finished page, asked what it would say if the hp had gone the
   other way. 'end' is reached by winning and losing alike, so this is the
   comparison C-1422 exists to add - interrogated on the product's own
   predicate rather than re-implemented out here. */
let asWin = null;
try { const keepP = p.hp, keepE = e.hp; p.hp = 3; e.hp = 0;
  asWin = recapFacts(); p.hp = keepP; e.hp = keepE }
catch (err) { asWin = 'error: ' + err.message }
console.log(JSON.stringify({ mode: MODE, facts: facts, asWin: asWin,
  recap: (typeof recapFacts === 'function') ? recapFacts() : null,
  state: state, winner: winner, frames: dFrame,
  said: dPaint.slice(0, 8) }));
"""


def loss_probe_source(script: str, *, mode: str = "beam", frames: int = 4000) -> str:
    """The page's own script, wrapped so both ways of losing can be driven."""

    return (
        LOSS_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("MODE_INPUT", json.dumps(mode))
        .replace("FRAMES_INPUT", str(int(frames)))
    )


#: A real volley on each duelist, and the sixty frames after it (§6 観察 2,
#: C-1377): the player's beam lands on the enemy through the trigger-time
#: rule, then the CPU's own volley lands on the player, and each blow must
#: flash the body, leave smoke that outlives the flash, and clear.
BEAT_PROBE = """
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
/* Watch one fighter for seventy frames after its hp drops. */
function watch(f, hpBefore){
  const trace = { hurtFrames: 0, smokeFrames: 0, smokeAfterHurt: 0, smokeLeft: 0 };
  for (let i = 0; i < 70; i++) { run(1);
    const b = beatFacts()[f];
    if (b.hurt > 0) trace.hurtFrames++;
    if (b.smoke > 0) { trace.smokeFrames++; if (b.hurt <= 0) trace.smokeAfterHurt++ } }
  trace.smokeLeft = beatFacts()[f].smoke;
  return trace;
}
/* The player's volley, by the trigger-time rule: charge, stand the CPU in
   the lane, fire. The CPU is stunned so nothing else moves the board. */
p.hold = true; run(40);
e.stun = 400; e.lane = p.lane; e.hold = false; e.beam = 0;
fire(p);
let eTrace = null, guard = 0;
while (e.hp === 3 && guard++ < 120) run(1);
if (e.hp < 3) eTrace = watch('e', 3);
/* Then the CPU's own volley on the player: stand still and take it. */
e.stun = 0;
let pTrace = null; guard = 0;
while (p.hp === 3 && guard++ < 2000) run(1);
if (p.hp < 3) pTrace = watch('p', 3);
console.log(JSON.stringify({ e: eTrace, p: pTrace,
  eHp: e.hp, pHp: p.hp }));
"""


def beat_probe_source(script: str) -> str:
    """The page's own script, wrapped so a blow on each duelist is read."""

    return BEAT_PROBE.replace("SCRIPT_PLACEHOLDER", script)
