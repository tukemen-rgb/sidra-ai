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

import json

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
/* §6 観察 3, brought home (C-1324): the guardian quickens past half
   health, the duel at match point, the shooter and marble by acts - and
   the kaiju, §6's own template, played all three cycles identically.
   The same multiplier table the siblings use, applied ONLY to how fast
   a crack opens: the 126-frame attack beat (§6 定量, read by the judge)
   and the 34-frame warning stay exactly as measured - the escalation
   must not eat the telegraph (the C-1318 line). */
const CYCLE_TENSE=[1,1.15,1.3];
function cycleTense(){return CYCLE_TENSE[Math.min(2,cycles)]}
let me,shots,boss,cracks,dust,t,state,cycles;
function reset(){
  /* Under the leg, not across the field (§8 事実 5): the first shot a
     new player fires has to hit something. Walking away is a choice
     they make after that, not a toll before it. */
  me={x:W*0.68,hp:3,step:0,cool:0,kvx:0,sq:1,mz:0};
  shots=[];cracks=[];dust=[];t=0;cycles=0;state='wake';
  boss={phase:'leg',legHp:LEGHP,head:-160,timer:BEAT,shown:false,hurt:0,smoke:0,smokeY:GROUND-70};}
setPal(KAIJU_PAL_TOKEN);
/* HUD contract (§4 WCAG 1.4.3, C-1334): draw() paints the HUD through
   these constants and hudFacts() reports them, so the metric can blend
   the plate over every measured sky the way the canvas does. The plate
   is the untinted theme surface at 0.7: the brightest final act was
   sinking the themed ink to ~3:1 here too (C-1329's fix, more templates). */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A}}
/* The far layer (§7 観察 7, C-1342): distance is drawn by CONTRAST, not
   colour - a skyline in the midground's own paint, faded toward the sky,
   sits behind the leg so the monster's scale has a horizon to dwarf. The
   ridge is a fixed function of x (no rand(): the layout every seed
   promised does not move), and it never animates, so reduced motion has
   nothing to freeze. draw() paints through FAR_A and depthFacts() reports
   the per-scene paints, the same contract shape as the HUD's. */
const FAR_A=0.22;
function depthFacts(){const keep=SCENE,out=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;
    out.push({sky:scenePaint('SURFACE_TOKEN'),solid:scenePaint('BORDER_TOKEN'),
      alpha:FAR_A})}
  SCENE=keep;return out}
/* The two smokes (§6 観察 2). The leg's 34 was C-1032's; the head's is
   that raised by the flash's own ratio (12/8), so the weighting the
   shake and the hitstop already carry is the weighting the smoke
   carries too. */
const LEG_SMOKE=34,HEAD_SMOKE=51;
function legX(){return W*0.72+Math.sin(t/90)*26}
function fire(){if(state!=='fight')return;
  /* A press during the cooldown is kept, not dropped (§12, C-1311): one
     queued shot, fired the frame the cannon is ready. */
  if(me.cool>0){me.queued=true;return}
  me.cool=11;
  /* The gun kicks (§1×§23 事実 3, C-1380): the cannon's push sinks the
     walker for a beat, through the same squash channel the stomp crush
     uses - settle, draw and the reduced-motion exemption all ride along
     for free. Softer than the crush (0.94 vs 0.7): a shot is not a hit. */
  if(!REDUCED){me.sq=Math.min(me.sq,0.94);
    /* 3, not 2: fire() runs from the key handler, so the step's decay
       ticks once before the first draw - three leaves two lit frames,
       the same two the shooter's in-step shoot() gets. */
    me.mz=3}
  shots.push({x:me.x,y:GROUND-26,vy:-7});sfx('fire')}
function hitLeg(){boss.legHp--;boss.hurt=8;boss.smoke=LEG_SMOKE;
  boss.smokeY=GROUND-70;shake(3);burst(legX(),GROUND-70,7,'ALERT_JUICE');
  sfx('cut',1,legX()/W);
  /* The leg buckling is the only way the head comes down. Three beats:
     flash, smoke that stays, silhouette back out of it (観察 2). */
  if(boss.legHp<=0){boss.phase='open';boss.head=GROUND-150;boss.timer=BEAT*2;
    hitstop(4);sfx('key')}}
/* The head takes the same three beats as the leg (§6 観察 2, C-1615).
   It had the flash and nothing else, while every other channel was
   already heavier for it - shake 3->7, hitstop 4->6 - so the biggest
   blow in the fight was the one that left no smoke. HEAD_SMOKE is the
   leg's 34 raised by the same ratio the flash is (12/8), and the
   height is caught HERE because the head retreats to -160 on the very
   next line: smoke hangs where the blow landed, not where the head
   went. */
function hitHead(){cycles++;boss.hurt=12;boss.smoke=HEAD_SMOKE;
  boss.smokeY=boss.head;shake(7);burst(legX(),boss.head,16,'ACCENT_JUICE');
  hitstop(6);sfx('sword');
  if(cycles>=3){state='won';boss.shown=true;boss.phase='down';winBeat(legX(),boss.head)}
  else{boss.phase='leg';boss.legHp=LEGHP;boss.head=-160;boss.timer=BEAT}}
function openCrack(){const x=60+rand()*(W-120);
  cracks.push({x:x,w:0,warn:34,open:0});sfx('charge')}
function step(rt){
  /* The world advances on real time, not on this display's refresh
     rate (§26, C-1608 — the gate C-1607 built and racing proved).
     Drawing is NOT gated: a 120Hz screen still gets 120 pictures a
     second, the world just stops happening twice as fast. */
  if(!TICK(rt)){draw();return requestAnimationFrame(step)}
  t++;
  combat(state==='fight'&&gateState()==='playing');
  /* The crush settles by quarter-steps and snaps (C-1332), outside the
     fight guard so a downed walker still stands back up. */
  me.sq+=(1-me.sq)*0.25;if(Math.abs(me.sq-1)<0.01)me.sq=1;
  if(me.mz>0)me.mz--;
  /* The awakening (§6 観察 3, C-1357): the film's escalation opens every
     encounter - cracks run, a dust wall rises, ONE wide shot shows the
     whole creature the leg belongs to, a beat, then the fight. Ninety
     frames, deterministic (no rand(): the seeded world must not shift),
     and quiet - combat() stays off until 'fight', so the §6 観察 4
     loudness step lands exactly when the film's does. */
  if(state==='wake'){
    if(t===1){sfx('hurt')}
    if(t<=30){if(t%6===0){cracks.push({x:W*0.12+t*W*0.025,w:0,warn:0,open:5+t*0.5})}}
    else if(t<=60){if(t%3===0){dust.push({x:(t*53)%W,y:GROUND-((t*29)%70),r:3+(t%5),a:1})}}
    else if(t===61){shake(9)}
    dust=dust.filter(d=>{d.a-=0.008;d.r+=0.15;return d.a>0});
    /* The ground closes as the fight opens: the prologue's fissures are
       scenery, not hazards - left in place they paid graze for standing
       still and could eat the spawn (measured by the graze suite). */
    if(t>=90){state='fight';t=0;cracks=[]}
    draw();requestAnimationFrame(step);return}
  if(state==='fight'){
    if(me.cool>0){me.cool--;
      if(me.cool===0&&me.queued){me.queued=false;fire()}}
    /* The shared steering part (C-1114), with this game's own margin. */
    partsSteerX(me,2.1,30,W-30);
    partsThrowX(me,30,W-30);
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
    cracks.forEach(c=>{if(c.warn>0){c.warn--;
      if(c.warn===0){sfx('clash');
        /* Weight is stride and dust (§6 観察 2, C-1362): the footfall
           that splits the ground raises a plume and kicks the camera.
           Deterministic offsets - the seed's board never moves - and a
           shake between the leg hit's 3 and the lost heart's 6, §1's
           weight-proportional rule. The soldier's stride had this; the
           monster whose weight is the subject did not. */
        for(let i=0;i<6;i++){dust.push({x:c.x+((i*37)%60)-30,
          y:GROUND-((i*13)%24),r:3+(i%3),a:1})}
        shake(5)}}
      else c.open=Math.min(56,c.open+CRACK*cycleTense())});
    cracks=cracks.filter(c=>{
      /* The gap and the radius that would cost a heart, named once and
         handed to both the collision and the graze (C-1419). The radius
         is the expression it has always been - a crack half its own width
         plus ten - so standing near one is exactly as dangerous as it
         was; the band is what is new, and it sits strictly outside. */
      const gk=c.open*0.5+10,gd=Math.abs(c.x-me.x);
      const live=c.warn===0&&c.open>10;
      if(live&&gd<gk){
        /* One crack, two losses: the heart and the graze run. */
        grazeStruck(gd,gk);grazeLost();
        me.hp--;shake(6);sfx('hurt');hitstop(3);
        /* Knockback (§1, C-1361): the other half of the hitstop pair.
           The blast throws the soldier AWAY from the crack; the clamp
           below keeps a wall from turning the throw into a pin. Kept
           under REDUCED - position is gameplay, not decoration. */
        me.kvx=(me.x<c.x?-1:1)*6;
        /* The crush (§1, C-1332's recipe, C-1370): the fourth struck
           body. Under reduced motion the silhouette never changes. */
        if(!REDUCED)me.sq=0.7;
        if(me.hp<=0){state='lost';failBeat(me.x,GROUND-20)}return false}
      /* Outside the radius that would have hurt, inside the ribbon: the
         crack was stood beside rather than fled from. */
      if(live){grazeNear(c,gk,gd,me.x,GROUND-30)}
      return c.open<56});
    dust.forEach(d=>{d.r+=0.6;d.a-=0.03});dust=dust.filter(d=>d.a>0);}
  draw();requestAnimationFrame(step)}
function K(k){return keys[k]}
const keys={};
addEventListener('keydown',e=>{keys[e.key]=true;
  if(e.key===' '){fire();e.preventDefault()}
  if(e.key==='r'||e.key==='R')reset()});
addEventListener('keyup',e=>{keys[e.key]=false});
/* The awakening, as a fact (C-1357): where the prologue is, what it has
   put on screen, and whether this is the wide-shot beat. */
/* The awakening's fourth beat (§6 観察 3, C-1368): the film cuts from
   the wide shot to the cockpit before the fight re-accelerates. One
   constant carries the cut for draw() and the facts alike - the
   declared beat and the painted one cannot drift apart (C-1342's
   shared-constant guard). */
const REACT_AT=75;
function wakeFacts(){return {state:state,t:t,cracks:cracks.length,
  dust:dust.length,wide:state==='wake'&&t>55&&t<=REACT_AT,
  react:state==='wake'&&t>REACT_AT}}
/* The hit's other half, as a fact (§1, C-1361). */
function kbFacts(){return {kvx:me.kvx,x:me.x,hp:me.hp,sq:me.sq}}
/* The pilot's face, as a fact (§1, C-1363): the eyes lean at the
   monster's leg - the fight's whole subject - with a deadzone so
   standing under it reads as a straight look, and the blink is the
   contract's shared beat, pinned open under reduced motion. */
function faceFacts(){const lx=legX();
  return {look:lx>me.x+8?1:lx<me.x-8?-1:0,
    blink:FRAME(40,6,performance.now())===1}}
function bossFacts(){return{phase:boss.phase,cycles:cycles,shown:boss.shown,
  hurt:boss.hurt,smoke:boss.smoke,smokeY:boss.smokeY,
  tense:cycleTense(),growth:CRACK*cycleTense(),
  legHp:boss.legHp,beat:BEAT,state:state,hp:me.hp}}
function draw(){const now=performance.now();
  /* 埃 -> 閃光 -> 最大明度: the phase picks the air the fight happens in, and
     the brightest frame of the whole page is the one where it goes down
     (§7 観察 5-6). Mood only - the leg and the head still read by shape. */
  setScene(boss.phase==='leg'?0:boss.phase==='open'?1:2);
  cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(0,0,W,H);
  /* The ruined skyline, one haze-step off the sky (観察 7). */
  cx.globalAlpha=FAR_A;cx.fillStyle=scenePaint('BORDER_TOKEN');
  for(let fx=0;fx<W;fx+=48){
    const fh=22+20*Math.abs(Math.sin(fx*0.13+2));
    cx.fillRect(fx,GROUND-fh,34,fh)}
  cx.globalAlpha=1;
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
      cx.beginPath();cx.arc(lx,boss.smokeY,40,0,6.283);cx.fill();cx.globalAlpha=1}
    if(boss.phase==='open'){
      cx.fillStyle=boss.hurt>0?'#dfe7f5':'MAGENTA_TOKEN';
      cx.beginPath();cx.arc(lx,boss.head,34,0,6.283);cx.fill();
      cx.fillStyle='ALERT_JUICE';cx.beginPath();cx.arc(lx,boss.head,12,0,6.283);cx.fill()}}
  else{cx.fillStyle='BORDER_TOKEN';
    cx.beginPath();cx.moveTo(lx-160,GROUND);cx.lineTo(lx-40,GROUND-120);
    cx.lineTo(lx+70,GROUND-96);cx.lineTo(lx+180,GROUND);cx.closePath();cx.fill()}
  /* The one wide shot (§6 観察 1+3, C-1357): for thirty frames of the
     awakening the WHOLE creature stands on the horizon - legs, body,
     head - small against the sky and enormous against the cannon. The
     fight then returns to the leg, and the full body is not seen again
     until it is down. */
  if(state==='wake'&&t>55&&t<=REACT_AT){
    cx.fillStyle=scenePaint('BORDER_TOKEN');
    const wx=W*0.55,wh=H*0.72,wb=GROUND;
    cx.fillRect(wx-30,wb-wh*0.42,60,wh*0.42);
    [-20,16].forEach(o=>{cx.fillRect(wx+o-7,wb-wh*0.46,14,wh*0.46)});
    cx.fillRect(wx-44,wb-wh*0.78,88,wh*0.38);
    cx.beginPath();cx.arc(wx,wb-wh*0.86,26,0,6.283);cx.fill();
    cx.beginPath();cx.moveTo(wx+40,wb-wh*0.55);cx.lineTo(wx+150,wb-wh*0.30);
    cx.lineTo(wx+44,wb-wh*0.38);cx.closePath();cx.fill()}
  /* The reaction shot (観察 3's 4th beat, C-1368): a framed cockpit
     insert, the pilot four times life size, eyes wide open at the
     monster - no blink in this beat, a held stare. A still frame, so
     reduced motion has nothing to freeze. */
  if(state==='wake'&&t>REACT_AT){
    const ix=W*0.30,iy=48,iw=W*0.40,ih=110;
    cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(ix,iy,iw,ih);
    cx.strokeStyle=scenePaint('BORDER_TOKEN');cx.lineWidth=3;
    cx.strokeRect(ix,iy,iw,ih);cx.lineWidth=1;
    const hx=ix+iw/2,hb2=iy+ih-16;
    cx.fillStyle='CYAN_TOKEN';cx.fillRect(hx-64,hb2-26,128,26);
    cx.fillRect(hx-16,hb2-70,32,46);
    const lk=legX()>me.x?1:-1;
    cx.fillStyle='#05070f';
    cx.fillRect(hx-12+lk*4,hb2-58,8,10);
    cx.fillRect(hx+4+lk*4,hb2-58,8,10)}
  const gait=Math.sin(me.step*6.283);
  /* One feet-anchored transform for the whole walker (§1, C-1370):
     heights scale by sq, widths by (2-sq), and every factor is exactly
     1 when sq is 1 - the idle and reduced silhouettes are bit-identical
     to what they were before the crush existed. */
  const sq=me.sq,sqw=2-sq;
  cx.fillStyle='CYAN_TOKEN';
  cx.fillRect(me.x-16*sqw,GROUND-30*sq,32*sqw,18*sq);
  cx.fillRect(me.x-4*sqw,GROUND-42*sq,8*sqw,12*sq);
  /* Eyes in the canopy (§1, C-1363): the pilot watches the monster.
     Skipped only on the blink frame - under reduced motion the shared
     FRAME pins the beat to 0 and the eyes never close. */
  const face=faceFacts();
  if(!face.blink){cx.fillStyle='#05070f';
    cx.fillRect(me.x+(-3+face.look)*sqw,GROUND-39*sq,2*sqw,2*sq);
    cx.fillRect(me.x+(1+face.look)*sqw,GROUND-39*sq,2*sqw,2*sq)}
  cx.strokeStyle='CYAN_TOKEN';cx.lineWidth=3;
  [-10,10].forEach((o,i)=>{cx.beginPath();cx.moveTo(me.x+o*sqw,GROUND-14*sq);
    cx.lineTo(me.x+(o+(i?gait:-gait)*7)*sqw,GROUND);cx.stroke()});
  /* Muzzle flash (§1×§23 事実 4, C-1391): two frames of light at the
     cannon mouth, the same !REDUCED event as the kick's sink. */
  if(me.mz>0){cx.fillStyle='ACCENT_JUICE';cx.globalAlpha=0.85;
    cx.fillRect(me.x-4,GROUND-34,8,8);cx.globalAlpha=1}
  /* The trail (§1, C-1389): same afterimage pair as the shooter's shot -
     the walker's bolt climbs at the same 7px/frame, so the segments sit
     +7 and +14 behind, fading. Reduced motion draws the head alone. */
  shots.forEach(s=>{cx.fillStyle='ACCENT_JUICE';cx.fillRect(s.x-2,s.y-8,4,10);
    if(!REDUCED){cx.globalAlpha=0.26;cx.fillRect(s.x-1.5,s.y+2,3,7);
      cx.globalAlpha=0.12;cx.fillRect(s.x-0.75,s.y+9,1.5,7);cx.globalAlpha=1}});
  cx.fillStyle='MAGENTA_TOKEN';
  for(let i=0;i<me.hp;i++){cx.fillRect(12+i*18,10,14,10)}
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(W-198,5,194,20);cx.globalAlpha=1;
  cx.fillStyle=HUD_INK;cx.font='13px ui-monospace,monospace';
  cx.fillText('周期 '+cycles+'/3  脚 '+Math.max(0,boss.legHp),W-190,19);
  if(state!=='fight'){cx.fillStyle='SCRIM_TOKEN'+'d0';cx.fillRect(0,0,W,H);
    cx.fillStyle='INK_TOKEN';cx.font='20px ui-monospace,monospace';
    const a=state==='won'?'巨獣、沈黙。':'部隊は退いた。';
    cx.fillText(a,W/2-a.length*10,H/2-8);
    cx.font='13px ui-monospace,monospace';
    if((typeof roundAskReady!=='function'||roundAskReady())){const b='R でもう一度';cx.fillText(b,W/2-b.length*6.5,H/2+18)}}}
/* One tap from the result goes again (§8 事実 3). The keyboard restart
   above is the only one this template had, which on a phone meant the
   result screen was a dead end. */
/* A tap restarts a FINISHED go - not the awakening. Left as
   state!=='fight' the prologue reset on every tap, and a masher
   tapping through the opening was pinned at t<=15 for ever
   (measured: the first-success probe starved at 30s). */
cv.addEventListener('pointerdown',()=>{if(state==='won'||state==='lost')reset()});
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
/* Past the start screen: the gate holds every frame until pressed. */
const press = { key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} };
keyHandlers.forEach(fn => fn(press));
run(2);
/* Through the awakening (C-1357): this probe tests the FIGHT. */
run(92);
/* Wasted shots first: hitting the leg while the head is down is the only
   thing that works, so shooting the sky must move nothing. */
const before = bossFacts();
for (let i = 0; i < 40; i++) { shots.push({x: 10, y: 40, vy: -7}); run(1) }
const afterMisses = bossFacts();
/* Now fight it properly: put a shot where the leg is, every frame, and read
   what the rules do. Records whether the body was ever drawn while alive. */
let bodyWhileAlive = false, sawOpen = false, cyclesAt = [];
/* Per cycle: the fastest single-frame crack growth actually observed, and
   the warning length every crack was born with (§6, C-1324). The warn is
   decremented the same frame the crack appears, so a fresh crack reads 33
   of its 34 frames - a constant, unless the telegraph is shortened. The
   kill is so fast that no crack would ever spawn (the first arrives on
   frame 126), so each cycle is WATCHED under dodging before it is won. */
const cycleGrowth = [0, 0, 0], warnsSeen = [];
function trackCracks(){
  const cy = Math.min(2, bossFacts().cycles);
  cracks.forEach(c => {
    if (c._seen === undefined) { c._seen = true; warnsSeen.push(c.warn) }
    if (c._po !== undefined && c.open > c._po) {
      const g = c.open - c._po;
      if (g > cycleGrowth[cy]) cycleGrowth[cy] = g;
    }
    c._po = c.open;
  });
}
function watch(frames){
  for (let i = 0; i < frames && bossFacts().state === 'fight'; i++) {
    let danger = null;
    cracks.forEach(c => { if (Math.abs(c.x - me.x) < c.open * 0.5 + 40) danger = c });
    if (danger) { me.x = danger.x > 360 ? danger.x - 140 : danger.x + 140;
      me.x = Math.max(30, Math.min(690, me.x)) }
    run(1);
    trackCracks();
  }
}
let frame = 0;
for (let guard = 0; guard < 40 && bossFacts().state === 'fight'
     && bossFacts().cycles < 3; guard++) {
  /* Live with this cycle's cracks long enough to measure two of them. */
  watch(300);
  /* Then win the cycle the way the old probe always did. */
  const startCycle = bossFacts().cycles;
  for (let i = 0; i < 400 && bossFacts().state === 'fight'
       && bossFacts().cycles === startCycle; i++) {
    const f = bossFacts();
    if (f.shown && f.state === 'fight') bodyWhileAlive = true;
    if (f.phase === 'open') { sawOpen = true; shots.push({x: 0, y: 0, vy: 0}) }
    const aim = f.phase === 'open' ? -160 : -70;
    shots.push({x: Math.sin(i/90)*26 + 720*0.72, y: 320 - 46 + aim + 8, vy: 0});
    run(1); frame++;
    trackCracks();
  }
  if (bossFacts().cycles !== startCycle) cyclesAt.push(frame);
}
const end = bossFacts();
const palette = sceneFacts();
const hud = hudFacts();
console.log(JSON.stringify({
  sceneOrder: sceneOrder,
  scenes: palette.scenes,
  hud: hud,
  depth: depthFacts(),
  beat: end.beat, phaseStart: before.phase, legHpStart: before.legHp,
  cyclesAfterMisses: afterMisses.cycles, legHpAfterMisses: afterMisses.legHp,
  sawOpen: sawOpen, bodyWhileAlive: bodyWhileAlive,
  cycles: end.cycles, shown: end.shown, state: end.state, kills: cyclesAt.length,
  cycleGrowth: cycleGrowth,
  warnMin: warnsSeen.length ? Math.min.apply(null, warnsSeen) : null,
  warnMax: warnsSeen.length ? Math.max.apply(null, warnsSeen) : null,
  winBeats: winBeats(), failBeats: failBeats(),
}));
"""


#: The two blows, beat by beat (§6 観察 2, C-1615). A real fight is driven
#: past the awakening, the leg is struck and watched frame by frame, then
#: the leg is broken open and the HEAD is struck and watched the same way.
#: The film's grammar is three beats - flash, smoke that stays, silhouette
#: back out of it - and the head had only the first.
BEATS_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
PROBE_EARS_PLACEHOLDER
SCRIPT_PLACEHOLDER
PROBE_EYES_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { eeTick();
  const fn = queued; queued = null; fn((F++) * 16) } }
function key(type, k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers[type] || []).forEach(fn => fn(e));
}
key('keydown', ' '); key('keyup', ' ');
/* Past the awakening: the prologue hands over to 'fight' at about 90. */
for (let i = 0; i < 400 && bossFacts().state !== 'fight'; i++) run(1);
/* Watch one blow. Fire at the page's OWN aim (legX and GROUND are in
   scope - recomputing them from the probe's frame counter misses, because
   the page's t only advances during the fight) and keep firing until the
   blow actually registers: the leg by losing hp, the head by turning the
   cycle. Only then read the beats, so a stale flash from an earlier hit
   cannot be mistaken for this one. */
function strike(aim, kind){
  shots.length = 0;
  const before = bossFacts();
  let atHit = null, kick = 0;
  for (let i = 0; i < 400 && !atHit; i++) {
    shots.push({x: legX(), y: GROUND + aim + 8, vy: 0});
    /* Clear the camera's accumulator so this frame's reading is THIS
       frame's kick (C-1648). shake() keeps the max and decays it, so a
       crack opening (5) or a hit taken (6) a few frames earlier would
       otherwise sit on top of the leg's own 3 and invert the ladder.
       Only the probe's own view is cleared; the page is untouched. */
    SHAKE = 0;
    run(1);
    const b = bossFacts();
    if (kind === 'head' ? b.cycles !== before.cycles : b.legHp !== before.legHp) {
      atHit = b;
      kick = shakeAmount();
    }
  }
  if (!atHit) { return { landed: false } }
  shots.length = 0;
  let flashFrames = 0, smokeFrames = 0, smokeAfterFlash = 0;
  for (let i = 0; i < 200; i++) {
    const b = bossFacts();
    if (b.hurt > 0) flashFrames++;
    if (b.smoke > 0) smokeFrames++;
    if (b.smoke > 0 && b.hurt === 0) smokeAfterFlash++;
    if (b.hurt === 0 && b.smoke === 0) break;
    run(1);
  }
  return { landed: true, kick: kick, hurtAtHit: atHit.hurt, smokeAtHit: atHit.smoke,
    smokeY: atHit.smokeY, flashFrames: flashFrames, smokeFrames: smokeFrames,
    smokeAfterFlash: smokeAfterFlash, smokeLeft: bossFacts().smoke,
    phaseBefore: before.phase };
}
const leg = strike(-70, 'leg');
/* Break the leg open so the head comes down, then strike THAT. */
for (let i = 0; i < 2000 && bossFacts().phase !== 'open'; i++) {
  shots.push({x: legX(), y: GROUND - 70 + 8, vy: 0});
  run(1);
}
const openedAt = bossFacts().phase;
const cyclesBefore = bossFacts().cycles;
const head = strike(-160, 'head');
/* The blow rings at the leg and lights at the leg (§28, C-1658). */
const pair = earEye('cut', W);
console.log(JSON.stringify({
  pair: pair, leg: leg, head: head, opened: openedAt,
  cyclesBefore: cyclesBefore, cyclesAfter: bossFacts().cycles,
  ground: 320 - 46
}));
"""


def beats_probe(script: str) -> str:
    """The page's own script, wrapped so both blows can be watched."""

    from sidra_ai.creation.probekit import PROBE_EARS, PROBE_EYES

    return (
        BEATS_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("PROBE_EARS_PLACEHOLDER", PROBE_EARS)
        .replace("PROBE_EYES_PLACEHOLDER", PROBE_EYES)
    )



#: How often the WHOLE creature is on screen (§6 観察 1, C-1665).
#: "Giant" is made by not showing all of it: legs and tail crossing the
#: frame, and the full body saved for a moment. The awakening contract
#: checks that the wide shot happens; nothing checked that it then stops,
#: and drawing it every frame left 231 tests green.
#:
#: Counted off the canvas, not off the source: the wide shot is a body
#: 60 wide, shoulders 88 wide and a head of radius 26, all in one frame.
WIDE_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
let RECTS = [], ARCS = [];
const rec = new Proxy(function(){}, {
  get: (t, k) => {
    if (k === 'fillRect') return (x, y, w, h) => { RECTS.push(Math.round(w)) };
    if (k === 'arc') return (x, y, r) => { ARCS.push(Math.round(r)) };
    if (k === Symbol.toPrimitive) return () => 0;
    return nothing },
  set: () => true, apply: () => nothing });
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => rec }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
PROBE_SEND_PLACEHOLDER
/* One frame, and whether the whole creature stood in it. */
function frame(){
  RECTS = []; ARCS = [];
  if (queued) { const fn = queued; queued = null; fn((F++) * 16) }
  return RECTS.indexOf(60) >= 0 && RECTS.indexOf(88) >= 0 && ARCS.indexOf(26) >= 0 }
let wake = 0, fight = 0, wakeFrames = 0, fightFrames = 0;
/* 1. the awakening, before a shot is fired */
for (let i = 0; i < 400 && bossFacts().state !== 'fight'; i++) {
  if (frame()) wake++;
  wakeFrames++;
}
/* 2. the fight, watched rather than fought. Shooting ends the round in
   about twenty frames, and twenty frames of "it did not appear" is not
   evidence of anything; standing off keeps the creature cycling so the
   absence is measured over a real stretch. The cannon is kept alive
   because a death RESETS the page, and the fresh awakening draws the
   wide shot again - which would look exactly like the fault this is
   here to find. */
for (let i = 0; i < 900 && bossFacts().state === 'fight'; i++) {
  me.hp = 99;
  if (frame()) fight++;
  fightFrames++;
}
console.log(JSON.stringify({ wake: wake, fight: fight,
  wakeFrames: wakeFrames, fightFrames: fightFrames,
  ended: bossFacts().state, shown: bossFacts().shown }));
"""


def wide_probe(script: str) -> str:
    """The page's own script, wrapped so the wide shot can be counted."""

    from sidra_ai.creation.probekit import PROBE_SEND

    return (
        WIDE_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("PROBE_SEND_PLACEHOLDER", PROBE_SEND)
    )


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
/* Through the awakening (C-1357): these probes test the FIGHT. */
run(92);
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



#: The awakening, as watched (§6 観察 3, C-1357): press start and read
#: the prologue's own timeline - cracks running, the dust wall, the one
#: wide shot - then the handover to a fight that behaves like a fight.
WAKE_PROBE = """
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
run(6);
const early = wakeFacts();
run(40);
const mid = wakeFacts();
run(26);
const wideAt = wakeFacts();
run(10);
const reactAt = wakeFacts();
/* A shot fired during the prologue must land nowhere: fire() is gated
   on 'fight', so the soldier watches like the film's do. Read as an
   absolute count, not a delta - the first destruction fired at the GATE
   press and a differential taken later missed it behind the cooldown. */
key(' ');
const firedInWake = shots.length;
let toFight = null;
for (let i = 0; i < 60 && toFight === null; i++) { run(1);
  if (wakeFacts().state === 'fight') toFight = 82 + i }
run(30);
key(' ');
const after = { state: wakeFacts().state, phase: bossFacts().phase,
  shots: shots.length };
console.log(JSON.stringify({
  early: early, mid: mid, wideAt: wideAt, reactAt: reactAt,
  firedInWake: firedInWake, toFight: toFight, after: after,
}));
"""


def wake_probe(script: str) -> str:
    """The page's own script, wrapped so the awakening can be watched."""

    return WAKE_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The knockback, as played (§1, C-1361). A live crack is placed beside
#: the soldier - the same shape the fight grows - and the throw is read
#: off kbFacts() frame by frame: away from the blast, settled inside half
#: a second, and pinned by the arena bound rather than pushed through it.
#: Direct state ops are the racing/guard probes' precedent (C-1306).
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
run(110);
/* Quiet the stomp clock so the one placed blast is the only one. */
boss.timer = 900; cracks.length = 0;
const x0 = me.x, hpBefore = me.hp;
cracks.push({ x: me.x + 4, w: 0, warn: 0, open: 30 });
run(1);
const onHit = kbFacts();
const track = [];
for (let i = 0; i < 40; i++){ run(1); track.push(kbFacts().x) }
const settled = kbFacts();
/* The wall case: parked on the left bound with the blast to the right,
   the throw points into the wall and the bound must hold. */
boss.timer = 900; cracks.length = 0;
me.x = 30; me.kvx = 0; me.hp = 3;
cracks.push({ x: me.x + 4, w: 0, warn: 0, open: 30 });
run(1);
let minX = 1e9;
for (let i = 0; i < 40; i++){ run(1); minX = Math.min(minX, kbFacts().x) }
console.log(JSON.stringify({
  x0: x0, hpBefore: hpBefore, onHit: onHit,
  moved: x0 - Math.min.apply(null, track),
  settledKvx: settled.kvx, hpAfter: settled.hp, minX: minX,
}));
"""


#: The cannon's kick, watched frame by frame (§1×§23 事実 3, C-1380):
#: one real shot in the fight must sink the walker through the squash
#: channel and settle back to 1; under reduced motion nothing sinks.
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
function key(k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' ');
run(110);
/* No stomp in the window, so the sink can only be the cannon's. */
boss.timer = 900; cracks.length = 0;
const idle = kbFacts().sq;
me.cool = 0;
key(' ');
const onFire = kbFacts().sq;
const trace = [];
for (let i = 0; i < 30; i++){ run(1); trace.push(kbFacts().sq) }
console.log(JSON.stringify({ state: state, idle: idle, onFire: onFire,
  trace: trace, shots: shots.length }));
"""


def kick_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the cannon's sink can be watched."""

    return KICK_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The trail, as painted (§1, C-1389): the walker's bolt climbs at the
#: same 7px/frame as the shooter's shot, so the same contract holds - a
#: full-alpha head with two fading afterimages one and two flight-steps
#: behind, and under reduced motion the head alone.
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
function key(k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' ');
run(110);
boss.timer = 900; cracks.length = 0;
me.cool = 0;
key(' ');
const fired = shots.length;
let watched = 0, headFrames = 0, fullTrail = 0, ghosts = 0;
for (let i = 0; i < 20 && shots.length; i++) {
  frameFills = []; run(1);
  const s = shots[0]; if (!s) break; watched++;
  if (frameFills.some(f => f[0] === s.x - 2 && f[1] === s.y - 8 &&
    f[2] === 4 && f[3] === 10 && f[4] === 1)) headFrames++;
  const t1 = frameFills.some(f => f[0] === s.x - 1.5 && f[1] === s.y + 2 &&
    f[2] === 3 && f[3] === 7 && f[4] === 0.26);
  const t2 = frameFills.some(f => f[0] === s.x - 0.75 && f[1] === s.y + 9 &&
    f[2] === 1.5 && f[3] === 7 && f[4] === 0.12);
  if (t1 && t2) fullTrail++;
  ghosts += frameFills.filter(f => (f[4] === 0.26 || f[4] === 0.12) &&
    Math.abs(f[0] - s.x) < 5).length;
}
console.log(JSON.stringify({ state: state, fired: fired, watched: watched,
  headFrames: headFrames, fullTrail: fullTrail, ghosts: ghosts }));
"""


def trail_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the bolt's trail can be watched."""

    return TRAIL_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The muzzle flash, as painted (§1×§23 事実 4, C-1391): one real shot
#: must light the cannon mouth for exactly two frames at 0.85 alpha, and
#: reduced motion fires the same shot with the mouth dark.
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
function key(k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
function flashNow(){ return frameFills.some(f => f[2] === 8 && f[3] === 8 &&
  f[4] === 0.85 && f[0] === me.x - 4 && f[1] === GROUND - 34) }
key(' ');
run(110);
boss.timer = 900; cracks.length = 0;
frameFills = []; run(1);
const idleFlash = flashNow();
me.cool = 0;
key(' ');
const lit = [];
for (let i = 0; i < 4; i++) { frameFills = []; run(1); lit.push(flashNow()) }
console.log(JSON.stringify({ state: state, shots: shots.length,
  idleFlash: idleFlash, lit: lit }));
"""


def muzzle_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the cannon light can be watched."""

    return MUZZLE_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The leg hit, heard where the leg stands (§2 増築, C-1394): one
#: engineered hit on the pacing leg, and the recorded pan must match
#: (legX()/W*2-1)*0.8 - to the right of centre, where the monster is -
#: while everything before it (wake roar, crack charge) stayed centred.
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
function key(k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' ');
run(110);
boss.timer = 900; cracks.length = 0;
const before = pans.length;
shots.push({ x: legX(), y: GROUND - 70, vy: 0 });
run(1);
const expected = (legX() / W * 2 - 1) * 0.8;
console.log(JSON.stringify({ state: state, before: before,
  legHp: boss.legHp, pans: pans, expected: expected }));
"""


def pan_probe(script: str) -> str:
    """The page's own script, wrapped so the leg hit's stereo position
    can be read off the audio graph."""

    return PAN_PROBE.replace("SCRIPT_PLACEHOLDER", script)


def kb_probe(script: str) -> str:
    """The page's own script, wrapped so the throw can be measured."""

    return KB_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The footfall's weight, as played (§6 観察 2, C-1362). The fight is run
#: to its first slam - the frame a crack's warning reaches zero and the
#: ground splits - and the plume is read where the foot came down: dust
#: near the crack the moment it opens, a camera kick on the same frame,
#: and a plume that clears instead of fogging the arena.
STOMP_PROBE = """
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
let shakes = 0;
const realShake = shake;
shake = (...a) => { shakes++; return realShake(...a) };
key(' ');
run(110);
/* March to the first slam: the warning is on the page, so the probe
   waits for it to reach zero rather than counting the clock itself. */
let slam = null, shakesAt = 0, dustAt = 0, near = 0, cx0 = null;
for (let i = 0; i < 400 && slam === null; i++) {
  const before = { shakes: shakes, dust: dust.length };
  const warned = cracks.filter(c => c.warn > 0).map(c => c.x);
  run(1);
  const opened = cracks.filter(c => c.warn === 0 && warned.indexOf(c.x) >= 0);
  if (opened.length) { slam = i; cx0 = opened[0].x;
    shakesAt = shakes - before.shakes;
    dustAt = dust.length - before.dust;
    near = dust.filter(d => Math.abs(d.x - cx0) <= 40).length }
}
/* The plume clears: no fresh stomp for a while, so only decay runs. */
let cleared = null;
if (slam !== null) {
  boss.timer = 9000;
  const plume = () => dust.filter(d => Math.abs(d.x - cx0) <= 40).length;
  for (let i = 0; i < 400 && cleared === null; i++) { run(1);
    if (plume() === 0) cleared = i }
}
console.log(JSON.stringify({ slam: slam, dustAt: dustAt, near: near,
  shakesAt: shakesAt, cleared: cleared }));
"""


def stomp_probe(script: str) -> str:
    """The page's own script, wrapped so the footfall can be weighed."""

    return STOMP_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The crush, as played (§1, C-1370). The walker idles untouched for
#: thirty frames (silhouette factor exactly 1 on every one), takes one
#: blast, crushes to 0.7 on the hit frame, and stands back to exactly 1
#: inside half a second; the reduced run takes the same blast and never
#: deforms a single frame. KB_PROBE's harness, with the beat quieted so
#: the one placed blast is the only impact.
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
run(110);
boss.timer = 900; cracks.length = 0;
run(1);
restFills = RECTS.slice();
let idleOff = 0, idleDrawn = 0, hitDrawn = 0;
for (let i = 0; i < 30; i++) { run(1); if (kbFacts().sq !== 1) idleOff++;
  if (followed(0.7)) idleDrawn++ }
cracks.push({ x: me.x + 4, w: 0, warn: 0, open: 30 });
run(1);
const hitSq = kbFacts().sq;
if (hitSq < 0.95 && followed(hitSq)) hitDrawn++;
let settled = null;
for (let i = 0; i < 40 && settled === null; i++) { run(1);
  if (kbFacts().sq < 0.95 && followed(kbFacts().sq)) hitDrawn++;
  if (kbFacts().sq === 1) settled = i }
console.log(JSON.stringify({ hitDrawn: hitDrawn, idleDrawn: idleDrawn,
  restFills: restFills.length, idleOff: idleOff, hitSq: hitSq,
  settled: settled, hp: kbFacts().hp }));
"""


def squash_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the crush can be watched."""

    return SQUASH_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The pilot's face, driven (§1, C-1363). The walker is parked on either
#: side of the monster's leg and dead under it, and the look is read off
#: the page; then it stands still for five hundred frames and the blink
#: is counted. The probe's clock ticks with the frames - a zero-pinned
#: performance.now freezes the wall-clock FRAME (C-1348's lesson).
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
function key(k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' ');
run(110);
me.x = 60; run(1);
const legRight = faceFacts().look;
me.x = 660; run(1);
const legLeft = faceFacts().look;
me.x = legX(); run(0);
const underLeg = faceFacts().look;
/* Stand still and count the blink. */
let blinkFrames = 0, longest = 0, streak = 0;
for (let i = 0; i < 500; i++) { run(1);
  if (faceFacts().blink) { blinkFrames++; streak++;
    if (streak > longest) longest = streak } else { streak = 0 } }

/* Which painted marks ARE the eyes, without knowing their size in advance
   (C-1634). Two frames that differ only in the blink: the marks the blink
   takes away are the face. Among the small ones, exactly one size occurs
   exactly twice - a left eye and a right eye - and that is the pair. Other
   things can blink on the same beat (the duel's dashed lane line puts 38
   identical squares in this difference), so "exactly twice" is what picks
   the eyes out rather than "small and gone". */

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
  legRight: legRight, legLeft: legLeft, underLeg: underLeg,
  blinkFrames: blinkFrames, longestBlink: longest,
}));
"""


def face_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the pilot's gaze can be read."""

    return FACE_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


__all__ = [
    "WAKE_PROBE",
    "wake_probe",
    "KB_PROBE",
    "KICK_PROBE",
    "TRAIL_PROBE",
    "MUZZLE_PROBE",
    "PAN_PROBE",
    "kick_probe",
    "trail_probe",
    "muzzle_probe",
    "pan_probe",
    "kb_probe",
    "SQUASH_PROBE",
    "squash_probe",
    "STOMP_PROBE",
    "stomp_probe",
    "FACE_PROBE",
    "face_probe",
    "BEATS_PROBE",
    "beats_probe",
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


#: Fights the real generated boss three ways, so what the graze band does
#: is read off a page that played rather than off this source. The player
#: is steered by pressing the arrow keys the template listens for - not by
#: writing to ``me.x`` - so the probe cannot reach a position the game
#: would not let a person reach.
#:
#: ``mode``: ``hug`` stands at the outer edge of the ribbon around the
#: nearest live crack, ``clear`` keeps to the far side of the arena, and
#: ``crash`` walks into the crack on purpose.
GRAZE_PROBE = """
const kNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : kNothing),
  apply: () => kNothing, set: () => true });
const kHandlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT, addEventListener(){}, addListener(){} });
let kClock = 0;
globalThis.performance = { now: () => kClock };
globalThis.addEventListener = (type, fn) => { (kHandlers[type] = kHandlers[type] || []).push(fn) };
globalThis.Image = function(){ return kNothing };
const kStore = {};
globalThis.localStorage = { getItem: (k) => (k in kStore ? kStore[k] : null),
  setItem: (k, v) => { kStore[k] = String(v) }, removeItem: (k) => { delete kStore[k] } };
globalThis.location = { reload: () => {} };
globalThis.KeyboardEvent = function(type, init){ return Object.assign({ type: type }, init) };
globalThis.dispatchEvent = (ev) => { (kHandlers[ev.type] || []).forEach(fn => fn(ev)); return true };
globalThis.document = { readyState: 'complete', body: { children: [] },
  createElement: () => kNothing, querySelector: () => null,
  getElementById: () => ({ width: 720, height: 320, style: {},
    addEventListener: () => {},
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => kNothing }) };
let kQueued = null;
globalThis.requestAnimationFrame = (fn) => { kQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
const MODE = MODE_INPUT;
let kFrame = 0;
function kRun(n){ for (let i = 0; i < n && kQueued; i++) {
  const fn = kQueued; kQueued = null; kClock += 50 / 3; fn(kFrame++ * 16) } }
function kKey(type, k){ (kHandlers[type] || []).forEach(fn => fn({ key: k === 'Space' ? ' ' : k, code: k === ' ' ? 'Space' : k,
  preventDefault(){}, stopImmediatePropagation(){} })) }
kKey('keydown', ' '); kKey('keyup', ' ');
kRun(94); /* through the awakening (C-1357) */
kRun(2);
/* The crack the player would meet, and the radius that would cost a heart -
   both read off the page's own state, using the page's own expression, so
   the probe cannot drift from the collision the template runs. */
function kNearest(){ let best = null, bd = 1e9;
  cracks.forEach(c => { if (!(c.warn === 0 && c.open > 10)) return;
    const d = Math.abs(c.x - me.x);
    if (d < bd) { bd = d; best = c } });
  return best ? { crack: best, dist: bd, kill: best.open * 0.5 + 10 } : null }
/* What a given spot on the ground is worth, against every live crack at
   once. Standing beside one crack is no good if it puts you inside
   another, and the arena is narrow enough that this happens. */
function kSpot(x){ let margin = 1e9, inBand = false, hurt = false;
  cracks.forEach(c => { if (!(c.warn === 0 && c.open > 10)) return;
    const kill = c.open * 0.5 + 10, d = Math.abs(c.x - x);
    if (d < kill) { hurt = true; return }
    if (d <= kill + BAND_INPUT) { inBand = true }
    margin = Math.min(margin, d - kill) });
  return { hurt: hurt, inBand: inBand, margin: margin } }
/* Where this mode wants to stand, chosen by scanning the ground rather
   than by stepping off one crack - hug wants the safest spot that is
   still inside a ribbon, clear wants the safest spot there is, and crash
   walks at the nearest crack. None of them writes to me.x: the arrow keys
   are pressed and the template moves the player, so the probe can only
   reach places a person could. */
function kWant(){
  if (MODE === 'crash') { const near = kNearest(); return near ? near.crack.x : null }
  let best = null, bestValue = -1e9;
  for (let x = 30; x <= 690; x += 4) {
    const spot = kSpot(x);
    if (spot.hurt) continue;
    const reach = Math.abs(x - me.x) * 0.05;
    const value = MODE === 'clear'
      ? Math.min(spot.margin, 200) - reach
      : (spot.inBand ? 1000 : 0) + Math.min(spot.margin, BAND_INPUT) - reach;
    if (value > bestValue) { bestValue = value; best = x } }
  return best }
const timeline = [];
let held = null;
for (let f = 0; f < FRAMES_INPUT; f++) {
  const want = kWant();
  let press = null;
  if (want !== null) { const gap = want - me.x;
    if (gap < -1.5) press = 'ArrowLeft'; else if (gap > 1.5) press = 'ArrowRight' }
  if (press !== held) {
    if (held) kKey('keyup', held);
    if (press) kKey('keydown', press);
    held = press }
  const before = grazeFacts();
  kRun(1);
  const after = grazeFacts();
  if (after.seen !== before.seen || after.paid !== before.paid
      || after.struck.length !== before.struck.length) {
    timeline.push({ f: f, seen: after.seen, paid: after.paid, run: after.run,
      hp: bossFacts().hp,
      hit: after.struck.length !== before.struck.length });
  }
  if (bossFacts().state !== 'fight') break;
}
if (held) kKey('keyup', held);
const facts = grazeFacts();
console.log(JSON.stringify({ mode: MODE, graze: facts, timeline: timeline,
  hp: bossFacts().hp, cycles: bossFacts().cycles, state: bossFacts().state,
  roundScore: roundScore(), frames: kFrame }));
"""


def graze_probe_source(
    script: str, *, mode: str = "hug", frames: int = 2000, reduced: bool = False
) -> str:
    """The page's own script, wrapped so the boss can be fought in node."""

    from sidra_ai.creation.graze import GRAZE_BAND

    return (
        GRAZE_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("MODE_INPUT", json.dumps(mode))
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("BAND_INPUT", str(GRAZE_BAND))
        .replace("REDUCED_INPUT", "true" if reduced else "false")
    )
