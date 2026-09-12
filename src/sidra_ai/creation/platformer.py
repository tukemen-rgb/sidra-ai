"""The side-scrolling platformer - gravity, and the small lies that make it fair.

「プラットフォーマー／横スクロール」 sat on the apology side of the genre
table: the honesty machinery named the gap on every request. The genre's whole
craft is in the jump, and the two mechanics every playable platformer ships
are deliberately *not* physics:

* **Coyote time.** For a few frames after the feet leave a ledge, the jump
  still works. Without it, an edge jump pressed one frame late reads as the
  game eating the input, because the player's model of "on the ledge" runs a
  few frames behind the pixels. Six frames here, and the probe jumps late on
  purpose to prove the window is real - and closed after it passes, or the
  game has silent double jumps.
* **Variable height.** Releasing early caps the rise, so the press length is
  the throttle. A fixed arc makes every gap the same decision; the cut is
  what turns "jump" into "how much".

The rest follows the knowledge base. Falling costs a walk back to the last
lit lantern, never the run (§1's feel over punishment - an instant game over
would spend the player's patience on the physics). Gems are a tap with a
sink (§5): five of them light the lantern that moves the respawn point, so
detouring for one is a decision about insurance. Platforms read by value and
edge against the backdrop, never by hue alone (§4). The course runs through
three scene palettes and the goal stretch is the brightest (§7 観察 5-6).
And there is **no fight in this template**, so it never calls ``combat`` -
a template must not claim a loudness step for a fight it does not have.

Token contract, shared with every template: ``SPEED_TOKEN`` is the gap
multiplier, ``BAND_TOKEN`` the platform count, ``SEED_TOKEN`` the layout
seed (same request, same course). ``REDUCED``/``FRAME`` come from the
animation preamble - the gem bob and the flag wave freeze while the game
keeps running - and ``sfx``/``shake``/``hitstop``/``burst`` from the audio
and juice preambles.
"""

from __future__ import annotations
from sidra_ai.creation.probekeys import KEY_EVENT_JS

import json

#: Words that pick this template. 「横スクロール」 routes here only when no
#: earlier genre claims the sentence: 「横スクロールシューティング」 is a
#: shooter, and both the router and the honesty table say so.
#:
#: The bare 「ジャンプ」/「跳」/「飛び越え」 belong here too (C-1220): a jump
#: is the one verb this template is *about*, yet the list only had the
#: compound 「ジャンプアクション」, so 「猫がジャンプするゲーム」 detected no
#: genre and fell to the default fishing template with no substitution notice.
#: Platformer is matched after shooter/adventure/racing/duel, so a sentence
#: that names one of those keeps it - 「ジャンプで撃つシューティング」 is still
#: a shooter - and only a request whose sole genre cue is the jump lands here.
#:
#: 「マリオ」 is here for the same reason 「ゼルダ」 is an adventure word
#: (C-1225): the flagship of the genre names the genre, so a franchise request
#: is one we *can* build - a jumping platformer - and routing it here lets the
#: title guard (``trademark_in``) swap the name for an original one, instead of
#: the request falling silently to fishing. Platformer is matched last, so
#: 「マリオカートのレース」 still lands on racing, which is named first.
PLATFORMER_WORDS: tuple[str, ...] = (
    "プラットフォーマー",
    "platformer",
    "横スクロール",
    "ジャンプアクション",
    "ジャンプ",
    "跳",
    "飛び越え",
    "足場",
    "マリオ",
)

#: (gap multiplier, platform count). Wider gaps ask more of the jump, more
#: platforms make the course longer - both grow toward hard.
PLATFORMER_DIFFICULTY: dict[str, tuple[float, float]] = {
    "easy": (0.8, 10),
    "normal": (1.0, 12),
    "hard": (1.25, 14),
}

PLATFORMER_TITLE = "はねる灯り"
PLATFORMER_HOW = (
    "← → で走り、↑ か SPACE でジャンプ。押す長さで高さが変わる。"
    "足場を渡ってゴールの旗まで。宝石 5 個で灯籠が点き、落ちてもそこから再開。"
    "R でやり直し、M で消音。"
)

#: The whole game. Rendered into the shared page shell; the audio, juice,
#: scene and pad preambles are prepended by ``generate_game`` like every
#: template. No ``combat(...)`` call anywhere in this script, on purpose.
PLATFORMER_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const GAPF=SPEED_TOKEN,NPLAT=BAND_TOKEN,SEED=SEED_TOKEN;
const W=cv.width,H=cv.height;
/* The three numbers that make the jump readable: 6 coyote frames after
   the feet leave a ledge, an early release capped to CUT (早離しで低く),
   and 5 buffer frames - a jump pressed and held just before landing fires
   on the exact landing frame instead of being dropped (§12, C-1310).
   Coyote and buffer are the two halves of the same forgiveness. */
const GRAV=0.42,JUMP=-7.2,CUT=-2.6,RUN=2.4,COYOTE=6,BUFFER=5,LAMP_COST=5;
/* The camera (§27, C-1622). What this template had was pure
   position-locking - cam = me.x - 260, recomputed inside draw() - which
   Scroll Back names as the technique with 'plenty of view space in all
   directions' and no lookahead, and which jerks on a direction change
   because the world moves the instant the hero does. On a 720 canvas a
   hero pinned at 260 sees 460px ahead running right and 260px running
   left: the walk back to the lantern got 57% of the view the walk out
   did.
   CAM_LOOK is target-focus (§27 事実 5): the aim leans the way the hero
   faces, and me.look already carries that - C-1348 added it for the
   eyes. CAM_EASE is lerp-smoothing (§27 事実 4), which is also what
   stops the lean itself from snapping when the hero turns around.
   The anchor moves to the middle of the canvas: with a 260 anchor the
   lean only deepened the imbalance (550 ahead running right, 350 running
   left). Centred and leaning by 90, the hero sits at 270 facing right and
   450 facing left - 450px of view ahead EITHER way, where the old locked
   camera gave 460 one way and 260 the other. */
const CAM_LOOK=90,CAM_EASE=0.12;
function camAim(){return Math.max(0,Math.min(LW-W,me.x-W/2+CAM_LOOK*me.look))}
setPal(PLAT_PAL_TOKEN);
/* HUD contract (§4 WCAG 1.4.3, C-1337): draw() paints through these
   constants, so hudFacts() reports what the frame shows. The progress-
   stepped scene tints the sky and the goal stretch was sinking the
   themed ink to ~3.4:1; the plate is the UNtinted theme surface at 0.7.
   skies[] is the actual per-scene backdrop - BG here, not SURFACE. */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){const keep=SCENE,sk=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;sk.push(scenePaint('BG_TOKEN'))}
  SCENE=keep;return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A,skies:sk}}
/* seeded LCG: same request, same course - the regeneration promise. */
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
let plats,orbs,lamp,flag,LW,me,state,respawns,msg,msgT,SHELF,SHELF_BASE,cam;
function build(){
  /* The first and last ledges are fixed so the opening steps and the goal
     are always fair; the seed decides everything between them. Gaps stay
     under the arc's reach (RUN x airtime) at every difficulty. */
  plats=[{x:0,y:262,w:150}];
  /* The first gem sits on the starting ledge, within a step of where the
     player lands (§8 事実 5): the opening has to hand something over
     before it asks for anything. Everything after it is the seed's. */
  orbs=[{x:110,y:236,got:false}];
  let x=150,y=262;
  for(let i=0;i<NPLAT;i++){
    x+=Math.round((34+rand()*20)*GAPF);
    const w=Math.round(70+rand()*50);
    y=Math.max(150,Math.min(268,y+Math.round((rand()*2-1)*30)));
    plats.push({x:x,y:y,w:w});
    if(i%2===0){orbs.push({x:x+w/2,y:y-26,got:false})}
    x+=w}
  x+=Math.round(40*GAPF);
  plats.push({x:x,y:250,w:170});
  flag={x:x+130,y:250};LW=x+170;
  /* The soft lock (§3, C-1367): a shelf only skill opens. It hangs 56px
     over the HIGHEST platform of the middle stretch - inside the jump's
     61.7px reach from that base and outside it from everywhere lower -
     so the lock is the player's arc, not an item. The low road still
     runs to the flag underneath it (a lock the skilled can bypass is
     soft; one they must pass is the road itself). Seeded like the rest
     of the course: same words, same shelf. Pushed into the same arrays,
     so drawing, one-way landings and the lantern economy just work. */
  let hb=null;
  const slo=Math.floor(plats.length/3),shi=Math.floor(plats.length*2/3);
  for(let i=slo;i<=shi;i++){if(!hb||plats[i].y<hb.y)hb=plats[i]}
  const sy=Math.max(96,hb.y-56);
  /* Over the base's CENTRE, not its edge: the auto-runner's jumps all
     start where the floor runs out, and an edge-jump's arc crosses the
     shelf's height ~50px past the lip - a shelf there would board
     itself. Centred, it takes a deliberate standing jump from under it:
     the lock is the choice plus the arc. One platform, two gems. */
  SHELF=[{x:hb.x+hb.w/2-36,y:sy,w:72}];
  SHELF_BASE=hb;
  plats.push(SHELF[0]);
  orbs.push({x:hb.x+hb.w/2-20,y:sy-26,got:false,shelf:true},
    {x:hb.x+hb.w/2+20,y:sy-26,got:false,shelf:true});
  /* Where the lantern stands is where the price is asked, so it may not
     stand anywhere the price cannot be paid (§5, C-1714). Three separate
     rules used to decide how many gems lay behind it - every other
     platform carries one, the middle platform carries the lantern, and
     the lantern's own platform loses its gem - and none of them had ever
     been compared with LAMP_COST. Measured: the low road reached the
     lantern holding FOUR on easy and normal against a price of five, so
     the auto-runner walked past its own insurance and finished with six
     gems and an unlit lamp. The remaining two lay AFTER it: money that
     can never be that outlet's money.
     Start from the middle, as before, and walk right to the first
     platform that has the price behind it. The gem on the chosen
     platform is the one about to be filtered away, so it is not counted.
     Nothing else moves: the price, the shelf and the flag are unchanged. */
  let mid=plats[Math.floor((plats.length-1)/2)];
  for(let i=Math.floor((plats.length-1)/2);i<plats.length;i++){
    const p=plats[i],cx=p.x+p.w/2;
    if(orbs.filter(o=>!o.shelf&&o.x<cx-1).length>=LAMP_COST){mid=p;break}
    mid=p}
  lamp={x:mid.x+mid.w/2,y:mid.y,lit:false};
  /* the lantern's platform keeps no gem: two pickups in one spot would
     read as one */
  orbs=orbs.filter(o=>o.shelf||Math.abs(o.x-lamp.x)>1)}
/* The afterimage the run leaves (§1 の軌跡, C-1628). Same shape as
   marble's and racing's: at most ten samples, one per frame the hero
   actually moved, drained one per frame when it does not. So the streak's
   length IS the speed - a hero standing still has no tail at all, and a
   sprint has a longer one than a shuffle. */
let TRAIL=[];
function reset(){rs=(SEED>>>0)||1;build();state='play';respawns=0;TRAIL=[];
  me={x:60,y:230,vy:0,ground:false,coyote:0,buffer:0,held:false,gems:0,
    cpX:60,cpY:262,sq:1,look:1};
  /* Start ON the aim, not at zero: a run that opens by sliding the world
     into place would read as a glitch. */
  cam=camAim();
  say('足場を渡って、旗まで。')}
/* Long enough to READ (§4 増築, C-1395): 15 frames a character = the
   4 chars/second subtitle standard; the old 150 stays as the floor. */
function say(t){msg=t;msgT=Math.max(150,Math.round(t.length*15))}
/* The face, as a fact: which way the eyes point, whether they are lifted
   by the rise, and whether this frame is the blink (§1, C-1348). */
function faceFacts(){return {look:me.look,up:me.vy<-1,
  blink:FRAME(40,6,performance.now())===1}}
/* The far layer (§7 観察 7, C-1354): the ridge was already drawn - a
   0.4x parallax silhouette in the midground's own paint - but through a
   bare literal no instrument could see. Same contract shape as kaiju's
   and duel's: draw() paints through FAR_A, depthFacts() reports the
   per-scene paints, and the judge holds the ridge visible against the
   sky yet fainter than the platform lip it is made of. Bringing the
   ridge under the contract measured the old 0.22 BELOW the visibility
   bar in four theme/scene cells (default act0 1.012:1, terminal act1
   1.010:1 - the comment said contrast and the paint said no); 0.45
   holds every cell at >=1.032:1 while staying the lip's own paint at
   under half strength, so no platform is ever outshone by its horizon. */
const FAR_A=0.45;
/* The routes, as facts (§3, C-1367): the shelf, the base it hangs over,
   and whether its gems have been earned. */
function routeFacts(){return {shelf:SHELF.map(p=>({x:p.x,y:p.y,w:p.w})),
  base:{x:SHELF_BASE.x,y:SHELF_BASE.y,w:SHELF_BASE.w},
  gems:orbs.filter(o=>o.shelf).map(o=>o.got)}}
function depthFacts(){const keep=SCENE,out=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;
    out.push({sky:scenePaint('BG_TOKEN'),solid:scenePaint('RAISED_TOKEN'),
      alpha:FAR_A})}
  SCENE=keep;return out}
const keys={};
function K(k){return keys[k]}
function tryJump(){if(state!=='play')return;
  /* coyote>0 covers both "standing" and "just walked off": the window is
     refilled every grounded frame and spent one frame at a time in the air,
     so a late edge press lands and a mid-fall press does not - not right
     away. A press held while airborne is kept for BUFFER frames instead of
     dropped, and fires on the landing frame (§12). */
  /* §2 増築 (C-1394, C-1633): normalised against the SCREEN, because this
     template scrolls - a world x would hand sfx a number outside 0..1 for
     anything off-camera and pin it to the edge. */
  if(me.coyote>0){me.vy=JUMP;me.coyote=0;me.ground=false;
    sfx('catch',1,(me.x-cam)/W);
    /* Squash & stretch (§1, C-1332): the take-off stretches the body
       tall; under reduced motion the silhouette never changes. */
    if(!REDUCED)me.sq=1.25}
  else{me.buffer=BUFFER}}
function cutJump(){me.held=false;me.buffer=0;if(me.vy<CUT)me.vy=CUT}
addEventListener('keydown',e=>{keys[e.key]=true;
  if(e.key==='ArrowUp'||e.code==='Space'){if(!keyInForm(e))e.preventDefault();
    if(!me.held){me.held=true;tryJump()}}
  if(e.key==='r'||e.key==='R')reset()});
addEventListener('keyup',e=>{keys[e.key]=false;
  if(e.key==='ArrowUp'||e.code==='Space')cutJump()});
cv.addEventListener('pointerdown',()=>{
  if(state==='play'){if(!me.held){me.held=true;tryJump()}}else{reset()}});
cv.addEventListener('pointerup',()=>{cutJump()});
function step(rt){const now=performance.now();
  /* The world advances on real time, not on this display's refresh
     rate (§26, C-1608 — the gate C-1607 built and racing proved).
     Drawing is NOT gated: a 120Hz screen still gets 120 pictures a
     second, the world just stops happening twice as fast. */
  if(!TICK(rt)){draw(now);return requestAnimationFrame(step)}
  worldStep();
  if(state==='play'){
    const tx0=me.x,ty0=me.y;
    if(K('ArrowLeft')){me.x=Math.max(10,me.x-RUN);me.look=-1}
    if(K('ArrowRight')){me.x=Math.min(LW-10,me.x+RUN);me.look=1}
    const vBefore=me.vy;
    me.vy=Math.min(8,me.vy+GRAV);me.y+=me.vy;
    /* one-way platforms: solid only when the feet cross the top going down,
       so a jump from below never bonks and the arc stays the player's */
    let on=false;
    if(me.vy>=0){for(const p of plats){
      if(me.x>p.x-6&&me.x<p.x+p.w+6&&me.y>=p.y&&me.y-me.vy<=p.y+0.001){
        me.y=p.y;me.vy=0;on=true;break}}}
    if(on){
      if(!me.ground){sfx('step',1,(me.x-cam)/W);
        /* ...and the landing squashes it flat, in proportion to the
           impact - a hop dents, a drop flattens (§1, C-1332). */
        if(!REDUCED)me.sq=Math.max(0.55,1-vBefore*0.07);
        /* landing smoke, weight-proportional (§1): a hop puffs, a drop
           also kicks the camera a little */
        burst(me.x,me.y,Math.min(12,2+Math.round(vBefore)),'ACCENT_JUICE');
        if(vBefore>5)shake(2)}
      me.ground=true;me.coyote=COYOTE;
      /* The buffered jump: pressed a few frames early, still held, fired
         the frame the feet touch - the other half of the coyote window. */
      if(me.buffer>0&&me.held){me.buffer=0;tryJump()}}
    else{me.ground=false;if(me.coyote>0)me.coyote--}
    if(me.buffer>0)me.buffer--;
    /* The bounce settles on its own: exponential ease back to rest,
       snapped when the eye can no longer tell. */
    me.sq+=(1-me.sq)*0.25;if(Math.abs(me.sq-1)<0.01)me.sq=1;
    orbs.forEach(o=>{if(!o.got&&Math.abs(o.x-me.x)<14&&Math.abs(o.y-(me.y-10))<18){
      o.got=true;me.gems++;sfx('gem',1,(o.x-cam)/W);
      burst(o.x,o.y,10,'ACCENT_JUICE');
      say(me.gems>=LAMP_COST&&!lamp.lit
        ?'宝石 '+me.gems+' 個。灯籠を点けられる。':'宝石 '+me.gems+' 個。')}});
    /* The sink (§5): gems light the lantern that moves the respawn point.
       A collectible that buys insurance is a reason to detour for it. */
    if(!lamp.lit&&Math.abs(lamp.x-me.x)<18&&Math.abs(lamp.y-me.y)<26){
      if(me.gems>=LAMP_COST){me.gems-=LAMP_COST;lamp.lit=true;
        /* Lighting the lantern moves where you come back from - a power,
           not a pickup, so it rings the powerUp voice (§2, C-1346). */
        me.cpX=lamp.x;me.cpY=lamp.y;sfx('powerup',1,(lamp.x-cam)/W);
        burst(lamp.x,lamp.y-18,16,'ALERT_JUICE');
        say('灯籠がともった。落ちてもここから。')}
      else if(msgT<=0){say('灯籠は宝石 '+LAMP_COST+' 個で点く（いま '+me.gems+' 個）。')}}
    if(Math.abs(flag.x-me.x)<16&&me.y>flag.y-30&&me.y<=flag.y+2){
      state='goal';winBeat(flag.x,flag.y-30)}
    /* Falling costs a walk back, never the run: respawn at the last lit
       lantern (or the start), no game over. */
    if(me.y>H+40){respawns++;me.x=me.cpX;me.y=me.cpY-6;me.vy=0;me.coyote=0;
      sfx('hurt',1,(me.x-cam)/W);shake(4);hitstop(4);
      say(lamp.lit?'灯籠まで戻された。':'足場のはじめに戻された。')}
    /* The trail of the run that set the record (§11, C-1330): the course
       x is the progress, the height is what is remembered there. Sampled
       after the physics has settled the frame, so a respawn records the
       lantern, not the pit. Walking back overwrites a bucket - the trail
       means "where you were, here, last time". */
    ghostSample(me.x,me.y);
    /* Sampled after the physics has settled, like the ghost above, so a
       respawn does not leave a streak stretched across the pit. */
    if(!REDUCED&&(Math.abs(me.x-tx0)>0.5||Math.abs(me.y-ty0)>0.5)){
      TRAIL.push({x:me.x,y:me.y});if(TRAIL.length>10)TRAIL.shift()}
    else if(TRAIL.length){TRAIL.shift()}}
  if(state!=='play'&&TRAIL.length){TRAIL.shift()}
  /* The camera closes the gap to its aim every frame, in play and out
     of it, so the goal screen settles instead of freezing mid-slide
     (§27 事実 4). */
  cam+=(camAim()-cam)*CAM_EASE;
  draw(now);requestAnimationFrame(step)}
function seg(){return me.x<LW*0.34?0:me.x<LW*0.72?1:2}
function draw(now){
  /* 序盤 -> 中盤 -> ゴール前: progress picks the accent hue, and the goal
     stretch keeps the brightest値 for last (§7 観察 5-6). */
  setScene(seg());
  cx.fillStyle=scenePaint('BG_TOKEN');cx.fillRect(0,0,W,H);
  /* cam is state now (§27, C-1622); step() eases it toward camAim(). */
  /* distance is contrast, not colour (§7 観察 7): a faint far ridge on a
     slower scroll. FAR_A is the contract (C-1354), not decoration. */
  cx.globalAlpha=FAR_A;cx.fillStyle=scenePaint('RAISED_TOKEN');
  for(let i=-1;i<4;i++){const rx=i*300-((cam*0.4)%300);
    cx.beginPath();cx.moveTo(rx,H);cx.lineTo(rx+150,H-90);cx.lineTo(rx+300,H);
    cx.closePath();cx.fill()}
  cx.globalAlpha=1;
  /* Platforms read by VALUE and FORM (§4): bright walkable lip with an edge
     highlight over a darker body - never hue alone against the backdrop. */
  plats.forEach(p=>{const x=p.x-cam;if(x>W||x+p.w<0)return;
    cx.fillStyle=scenePaint('SURFACE_TOKEN');
    cx.fillRect(x,p.y+10,p.w,Math.max(4,Math.min(26,H-p.y-10)));
    cx.fillStyle=scenePaint('RAISED_TOKEN');cx.fillRect(x,p.y,p.w,10);
    cx.fillStyle='#ffffff2e';cx.fillRect(x,p.y,p.w,3);
    cx.fillStyle='#00000055';cx.fillRect(x,p.y+8,p.w,2)});
  orbs.forEach(o=>{if(o.got)return;const x=o.x-cam;if(x<-20||x>W+20)return;
    /* decorative: a four-frame bob, frozen under reduced motion */
    const bob=[0,-2,0,2][FRAME(4,6,now)];
    cx.fillStyle='CYAN_TOKEN';cx.beginPath();
    cx.moveTo(x,o.y-7+bob);cx.lineTo(x+6,o.y+bob);
    cx.lineTo(x,o.y+7+bob);cx.lineTo(x-6,o.y+bob);cx.closePath();cx.fill()});
  /* Shapes, not tints (§4): the lantern wears its price until it is lit. */
  const lx=lamp.x-cam;
  if(lx>-30&&lx<W+30){
    cx.fillStyle='BORDER_TOKEN';cx.fillRect(lx-2,lamp.y-26,4,26);
    cx.fillStyle=lamp.lit?'ALERT_JUICE':scenePaint('RAISED_TOKEN');
    cx.fillRect(lx-7,lamp.y-40,14,16);
    cx.strokeStyle='INK_TOKEN';cx.strokeRect(lx-7.5,lamp.y-40.5,15,17);
    /* A number written on the lamp, so it is ink like every other
       word on the page - white on a light theme is not readable (C-1131). */
    if(!lamp.lit){cx.fillStyle='INK_TOKEN';cx.font=hudPx(13)+'px ui-monospace,monospace';
      cx.fillText(String(LAMP_COST),lx-4,lamp.y-28)}}
  const fx=flag.x-cam;
  if(fx>-40&&fx<W+40){
    cx.fillStyle='INK_TOKEN';cx.fillRect(fx-1,flag.y-46,3,46);
    const wv=[0,2,4,2][FRAME(4,5,now)];
    cx.fillStyle='MAGENTA_TOKEN';cx.beginPath();
    cx.moveTo(fx+2,flag.y-46);cx.lineTo(fx+26+wv,flag.y-38);
    cx.lineTo(fx+2,flag.y-30);cx.closePath();cx.fill()}
  const px=me.x-cam;
  /* The past self, at this point of the course: drawn and nothing else -
     no collision, no score, no sound (C-1401's contract, third template
     by C-1330). At the hero's own screen x, at the height the record run
     had here, and before the hero, so the present is never hidden. */
  /* The second ghost (§11, C-1335): yesterday's height at this point
     of the course, an outline under the best. */
  const gly=ghostAtLast(me.x);
  if(gly!==null){cx.save();cx.globalAlpha=0.35;
    cx.strokeStyle=TUNE_ACCENT;cx.lineWidth=1;
    cx.strokeRect(px-7.5,gly-18.5,15,13);cx.restore()}
  const gy=ghostAt(me.x);
  if(gy!==null){cx.save();cx.globalAlpha=0.32;
    cx.fillStyle=TUNE_ACCENT;cx.fillRect(px-7,gy-18,14,12);
    cx.fillRect(px-3,gy-24,6,6);
    cx.globalAlpha=0.6;cx.strokeStyle=TUNE_ACCENT;cx.lineWidth=1;
    cx.strokeRect(px-7.5,gy-18.5,15,13);cx.restore()}
  /* The run's own afterimage (§1 の軌跡, C-1628), under the hero and over
     the record's ghost - it belongs to this run, not to the last one. */
  TRAIL.forEach((s,i)=>{const sx=s.x-cam;if(sx<-20||sx>W+20)return;
    cx.save();cx.globalAlpha=((i+1)/TRAIL.length)*0.34;
    cx.fillStyle='CYAN_TOKEN';cx.fillRect(sx-7,s.y-18,14,12);cx.restore()});
  /* Feet-anchored squash & stretch: height scales with sq, width the
     other way, so the volume reads constant and the feet never float. */
  const sqh=12*me.sq,sqw=14*(2-me.sq),sqt=me.y-6-sqh;
  cx.fillStyle='CYAN_TOKEN';cx.fillRect(px-sqw/2,sqt,sqw,sqh);
  cx.fillRect(px-3,sqt-6,6,6);
  /* Eyes that look where the run goes (§1, C-1348): the last technique
     on the juice list - a face is what makes a rectangle somebody. They
     shift with me.look, lift while rising, and shut for one beat every
     few seconds. Under reduced motion FRAME pins them open, so the face
     never animates there - the machinery every frozen sparkle uses. */
  if(!faceFacts().blink){cx.fillStyle='#05070f';
    const ex=me.look*1.5,ey=me.vy<-1?-1:0;
    cx.fillRect(px-2.5+ex,sqt-5+ey,1.5,2);
    cx.fillRect(px+1+ex,sqt-5+ey,1.5,2)}
  /* the gait is position-driven, so it only moves when the player does */
  const g2=me.ground?Math.sin(me.x/5)*4:3;
  cx.strokeStyle='CYAN_TOKEN';cx.lineWidth=2;
  cx.beginPath();cx.moveTo(px-3,me.y-6);cx.lineTo(px-3-g2,me.y);cx.stroke();
  cx.beginPath();cx.moveTo(px+3,me.y-6);cx.lineTo(px+3+g2,me.y);cx.stroke();
  cx.lineWidth=1;
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(34,4,330,hudBand(13,9));cx.globalAlpha=1;
  cx.fillStyle=HUD_INK;cx.font=hudPx(13)+'px ui-monospace,monospace';
  cx.fillText('宝石 '+me.gems+' / '+LAMP_COST+(lamp.lit?'  灯籠 点':'')
    +'  落下 '+respawns,40,4+hudBand(13,3));
  if(msgT>0){msgT--;cx.fillStyle='SCRIM_TOKEN'+'d9';cx.fillRect(20,H-34,W-40,26);
    cx.fillStyle='INK_TOKEN';cx.fillText(msg,30,H-16)}
  if(state==='goal'){cx.fillStyle='SCRIM_TOKEN'+'d0';cx.fillRect(0,0,W,H);
    cx.fillStyle='INK_TOKEN';cx.font=hudPx(20)+'px ui-monospace,monospace';
    const a='灯りは旗までとどいた。';
    cx.fillText(a,W/2-a.length*10,H/2-8);
    cx.font=hudPx(13)+'px ui-monospace,monospace';
    const b='宝石 '+me.gems+' 個 / 落下 '+respawns+' 回'+(((typeof roundAskReady!=='function'||roundAskReady()))?' / R かタップでもう一度':'');
    cx.fillText(b,W/2-b.length*6.5,H/2+18)}}
function platFacts(){return{x:me.x,y:me.y,vy:me.vy,ground:me.ground,
  squash:me.sq,
  trail:TRAIL.map(s=>s.x),trailY:TRAIL.map(s=>s.y),
  coyote:me.coyote,window:COYOTE,buffer:me.buffer,bufferWindow:BUFFER,
  gems:me.gems,respawns:respawns,
  lit:lamp.lit,cpX:me.cpX,state:state,lampX:lamp.x,lampY:lamp.y,
  flagX:flag.x,flagY:flag.y,world:LW}}
reset();step();
"""

#: The buffered jump, played (C-1310): pressed and held a few frames before
#: landing it fires on the landing frame; released before landing it is
#: discarded - and a press in open air still never jumps on the spot.
BUFFER_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const keyHandlers = [], upHandlers = [];
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => {
  if (type === 'keydown') keyHandlers.push(fn);
  if (type === 'keyup') upHandlers.push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn(i * 16) } }
function ev(key){ return probeKey(key) }
function press(key){ keyHandlers.forEach(fn => fn(ev(key))) }
function lift(key){ upHandlers.forEach(fn => fn(ev(key))) }
press(' '); lift(' '); run(80);
const g0 = platFacts().y;
/* Hop, and on the way back down - a couple of frames from the ledge -
   press and HOLD. The jump must fire the frame the feet touch. */
function hopThenPress(release){
  press('ArrowUp'); run(6); lift('ArrowUp');
  let guard = 0;
  while ((platFacts().vy < 0 || platFacts().y < g0 - 14) && guard++ < 300) run(1);
  press('ArrowUp');
  const at = platFacts();
  if (release) { lift('ArrowUp') }
  let jumped = false, frames = 0;
  for (let i = 0; i < 12; i++) { run(1);
    if (platFacts().vy < 0) { jumped = true; frames = i + 1; break } }
  if (!release) { lift('ArrowUp') }
  run(80);
  return { airborneAtPress: !at.ground && at.vy > 0, bufferAtPress: at.buffer,
    jumped: jumped, frames: frames };
}
const held = hopThenPress(false);
const released = hopThenPress(true);
/* Open air is still open air: a press high above the ground must not
   move the player upward on the spot. */
me.y = g0 - 120; me.vy = 0; me.ground = false; me.coyote = 0; run(1);
press('ArrowUp'); run(1);
const openAir = platFacts().vy > 0 || platFacts().y < g0 - 60 ? platFacts().vy >= 0 : false;
lift('ArrowUp');
console.log(JSON.stringify({ bufferWindow: platFacts().bufferWindow,
  held: held, released: released, openAirNoJump: openAir }));
"""


def buffer_probe(script: str) -> str:
    """The page's own script, wrapped so a buffered jump can be watched."""

    return BUFFER_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The page driven in node: the browser is a no-op proxy, the real script
#: runs, and the course is played - a late edge jump, a mid-fall jump, two
#: falls, the lantern and the flag - so the rules are read back instead of
#: grepped for. Every fake this template invites passes a source check: a
#: coyote window that never closes (a double jump), a jump cut that never
#: fires, a "respawn" that is a reload.
PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const keyHandlers = [], upHandlers = [];
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => {
  if (type === 'keydown') keyHandlers.push(fn);
  if (type === 'keyup') upHandlers.push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn(i * 16) } }
function ev(key){ return probeKey(key) }
function press(key){ keyHandlers.forEach(fn => fn(ev(key))) }
function lift(key){ upHandlers.forEach(fn => fn(ev(key))) }
/* Past the start screen, then settle onto the fixed first ledge. */
press(' '); lift(' '); run(80);
const settled = platFacts();
/* Full-hold jump vs an early release: the held apex must be higher, or the
   press length is a label and not a throttle. */
press('ArrowUp');
let heldMin = 1e9;
for (let i = 0; i < 40; i++) { run(1); heldMin = Math.min(heldMin, platFacts().y) }
lift('ArrowUp'); run(30);
press('ArrowUp'); run(3); lift('ArrowUp');
let tapMin = 1e9;
for (let i = 0; i < 40; i++) { run(1); tapMin = Math.min(tapMin, platFacts().y) }
run(30);
/* Coyote time, played: walk off the first ledge, wait two airborne frames,
   and the jump must still land. */
press('ArrowRight');
let leftGround = false;
for (let i = 0; i < 400; i++) { run(1); if (!platFacts().ground) { leftGround = true; break } }
lift('ArrowRight');
run(2);
press('ArrowUp'); run(1);
const coyoteJump = platFacts().vy < 0;
lift('ArrowUp');
/* The miss becomes the first fall: no game over, back to the start. */
let firstRespawn = null;
for (let i = 0; i < 400; i++) { run(1);
  if (platFacts().respawns > 0) { firstRespawn = platFacts(); break } }
/* And the window closes: ten airborne frames is past it, so the same press
   must do nothing - otherwise the game has a quiet double jump. Wait for
   the feet first: the respawn drops the player in from just above. */
for (let i = 0; i < 60; i++) { run(1); if (platFacts().ground) break }
press('ArrowRight');
for (let i = 0; i < 400; i++) { run(1); if (!platFacts().ground) break }
lift('ArrowRight');
run(10);
press('ArrowUp'); run(1);
const lateJumpRefused = platFacts().vy > 0;
lift('ArrowUp');
let secondRespawn = null;
for (let i = 0; i < 400; i++) { run(1);
  if (platFacts().respawns > 1) { secondRespawn = platFacts(); break } }
/* A gem pays in a number: stand where one floats and the count moves.
   (run past the respawn's hitstop, which holds the frame for a few beats) */
const orb = orbs.find(o => !o.got);
const gemsBefore = platFacts().gems;
me.x = orb.x; me.y = orb.y + 10; me.vy = 0; run(10);
const gemsAfterOrb = platFacts().gems;
/* The sink (§5): five gems light the lantern, the gems leave, and the
   respawn point moves to it. */
me.gems = 5;
me.x = lamp.x; me.y = lamp.y - 40; me.vy = 0; run(30);
const afterLamp = platFacts();
const fallsSoFar = platFacts().respawns;
me.y = 400;
let thirdRespawn = null;
for (let i = 0; i < 60; i++) { run(1);
  if (platFacts().respawns > fallsSoFar) { thirdRespawn = platFacts(); break } }
/* Which act the page was actually IN at each third of the course
   (C-1640). sceneFacts().scenes is the palette TABLE - three colours that
   exist - and the contract read only that, so a page that painted act 0
   from end to end passed it. This is the other half. */
const sceneOrder = [];
for (const third of [0.12, 0.5, 0.88]) {
  /* Standing ON something in each third: a hero dropped into thin air
     falls into the pit and respawns at the lantern, and then every sample
     reads the lantern's act. Three frames, not one, because a respawn's
     hitstop holds a frame and step() returns before draw(). */
  const want = LW * third;
  const stand = plats.reduce((a, b) =>
    (Math.abs(b.x + b.w / 2 - want) < Math.abs(a.x + a.w / 2 - want) ? b : a));
  me.x = stand.x + stand.w / 2; me.y = stand.y; me.vy = 0;
  me.ground = true; me.coyote = 0; run(8);
  const now = sceneFacts().scene;
  if (sceneOrder[sceneOrder.length - 1] !== now) { sceneOrder.push(now) }
}
/* The flag ends the run in a completed state, not another screen of play. */
me.x = flag.x; me.y = flag.y - 40; me.vy = 0; run(40);
const end = platFacts();
const palette = sceneFacts();
console.log(JSON.stringify({
  scenes: palette.scenes, sceneOrder: sceneOrder,
  hud: hudFacts(),
  depth: depthFacts(),
  window: settled.window, settledGround: settled.ground, groundY: settled.y,
  heldMin: heldMin, tapMin: tapMin,
  leftGround: leftGround, coyoteJump: coyoteJump, lateJumpRefused: lateJumpRefused,
  firstRespawnX: firstRespawn && firstRespawn.cpX,
  firstRespawnState: firstRespawn && firstRespawn.state,
  secondRespawn: secondRespawn !== null,
  gemsBefore: gemsBefore, gemsAfterOrb: gemsAfterOrb,
  lampLit: afterLamp.lit, gemsAfterLamp: afterLamp.gems,
  thirdRespawnX: thirdRespawn && thirdRespawn.x, lampX: afterLamp.lampX,
  state: end.state, respawns: end.respawns,
  combatOn: typeof combatOn === 'function' ? combatOn() : null,
  winBeats: winBeats(),
}));
"""



#: The two weights this page actually uses, driven for real (§1, C-1652).
#: A hop that lands hard kicks the camera by 2; falling into the pit kicks
#: it by 4. Vlambeer's rule is that the heavier event kicks harder, and
#: until now nothing here checked it - flattening both to one number left
#: every test green.
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
/* Which sounds this frame made, so the kick can be attributed to an
   event rather than to whatever else was on screen. */
let rang = [];
const realSfx = sfx;
sfx = function(name){ rang.push(String(name)); return realSfx.apply(this, arguments) };
/* Only a frame that rang this event and nothing else can attribute the
   kick to it (C-1652). shake() keeps the max WITHIN a frame too, and the
   combo step-up in combo.py kicks by 3, so a gate taken on the same frame
   as a step-up reads the combo's kick, not the gate's. Clearing SHAKE per
   frame fixes the history; this fixes the company. */
function alone(rang, name){ return rang.length === 1 && rang[0] === name }
function frame(){ rang = [];
  eeTick();
  return probeKick(() => { if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }) }
probeSend('keydown', ' ', handlers); probeSend('keyup', ' ', handlers);
frame(); frame();
function settle(n){ for (let i = 0; i < (n || 30); i++) { frame() } }

/* --- the light one: a drop that lands hard --- */
const pad = plats.reduce((a, b) => (b.w > a.w ? b : a));
let land = null;
me.x = pad.x + pad.w / 2; me.y = pad.y - 120; me.vy = 0; me.ground = false;
for (let i = 0; i < 90 && land === null; i++) {
  const airborne = !me.ground;
  const kick = frame();
  if (airborne && me.ground && alone(rang, 'step')) { land = { kick: kick, rang: rang.slice() } }
}
settle();

/* --- the heavy one: into the pit --- */
me.x = pad.x + pad.w / 2; me.y = H + 50; me.vy = 4; me.ground = false;
let fell = null;
for (let i = 0; i < 30 && fell === null; i++) {
  const kick = frame();
  if (alone(rang, 'hurt')) { fell = { kick: kick, rang: rang.slice() } }
}
/* A gem picked up: the sound is panned at the orb and the light is
   drawn at the orb, so ear and eye can be put side by side (§28,
   C-1653). The pit-fall sound is NOT used here - it draws no burst at
   all, because what the eye gets there is the hero itself reappearing
   at the lantern, and a missing burst is not a missing picture. */
const orb = orbs.filter(o => !o.got)[0];
if (orb) {
  /* Stand under the orb first and let the camera catch up: `cam` eases
     toward its target (C-1622), so a hero teleported and collected on
     the same frame is panned against a camera still hundreds of pixels
     behind - the probe would be measuring its own staging. */
  orb.got = true;
  for (let i = 0; i < 60; i++) {
    me.x = orb.x; me.y = orb.y + 10; me.vy = 0; me.ground = true; frame() }
  orb.got = false;
  for (let i = 0; i < 4 && !orb.got; i++) {
    me.x = orb.x; me.y = orb.y + 10; me.vy = 0; me.ground = true; frame() }
}
/* This page pans camera-relative (`(x-cam)/W`), so the light's world x
   is mapped the same way before the two are compared. */
const pair = earEye('gem', cv.width, function(x){ return (x - cam) / cv.width });
/* The dust is weighed too (§1, C-1660): `min(12, 2+round(vBefore))`, so a
   hop puffs and a drop throws up a cloud. Read as the page's own particle
   list growing, not as the number handed to burst - and read on a frame
   that rang this landing alone, because a combo step-up adds twelve of
   its own. */
function landFrom(height){
  settle();
  const pad2 = plats.reduce((a, b) => (b.w > a.w ? b : a));
  me.x = pad2.x + pad2.w / 2; me.y = pad2.y - height; me.vy = 0; me.ground = false;
  for (let i = 0; i < 200; i++) {
    const airborne = !me.ground;
    const before = PARTS.length;
    const fast = me.vy;
    rang = [];
    frame();
    if (airborne && me.ground) {
      return { height: height, vy: Math.round(fast * 100) / 100,
        parts: PARTS.length - before, rang: rang.slice() };
    }
  }
  return null;
}
const softDust = landFrom(24);
const hardDust = landFrom(200);
console.log(JSON.stringify({ pair: pair, softDust: softDust, hardDust: hardDust, light: land, heavy: fell }));
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


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the course can be played in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: Squash & stretch, watched frame by frame (§1, C-1332): one real jump.
#: The body must stretch past 1 while rising, squash below 1 on the exact
#: landing frame, settle back to rest within half a second - and under
#: reduced motion every sampled frame must read exactly 1, because the
#: silhouette is the one thing that run promises never changes.
SQUASH_PROBE = KEY_EVENT_JS + """
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

function kd(k){ (handlers.keydown || []).forEach(fn => fn(probeKey(k))) }
function ku(k){ (handlers.keyup || []).forEach(fn => fn(probeKey(k))) }
kd(' '); ku(' ');
run(10);
const restSq = platFacts().squash;
restFills = RECTS.slice();
let riseDrawn = 0, landDrawn = 0, idleDrawn = 0;
/* One full jump, held to the top, sampled every frame of the arc. */
kd(' ');
let riseMax = 0, guard = 0, landSq = null, wasAir = false;
while (guard++ < 400) {
  run(1);
  const f = platFacts();
  if (!f.ground) { wasAir = true; riseMax = Math.max(riseMax, f.squash);
    if (f.squash > 1.05 && followed(f.squash)) riseDrawn++ }
  if (wasAir && f.ground) { landSq = f.squash;
    if (f.squash < 0.95 && followed(f.squash)) landDrawn++;
    break }
}
ku(' ');
/* Half a second later the body is a body again. */
run(30);
const settled = platFacts().squash;
/* And the whole arc again with nothing pressed: standing still, the
   silhouette must not breathe on its own. */
let idleMax = 0;
for (let i = 0; i < 40; i++) { run(1);
  idleMax = Math.max(idleMax, Math.abs(platFacts().squash - 1));
  if (followed(0.7)) idleDrawn++ }
console.log(JSON.stringify({
  riseDrawn: riseDrawn, landDrawn: landDrawn, idleDrawn: idleDrawn,
  restFills: restFills.length,
  restSq: restSq, riseMax: riseMax, landSq: landSq,
  settled: settled, idleMax: idleMax,
}));
"""


def squash_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so one jump's shape can be watched."""

    return SQUASH_PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "SCRIPT_PLACEHOLDER", script
    )


#: The lantern's voice, as wired (§2, C-1346): lighting it moves the
#: respawn point - a power, not a pickup - so the moment it lights must
#: build the vibrato path. The AudioContext is the audio probe's Recorder:
#: connections, not constructions.
LAMP_SFX_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const played = [], nodes = [], freqs = [];
function Recorder(){ this.state='running'; this.currentTime=0; this.destination={};
  this.sampleRate=44100 }
Recorder.prototype.createPeriodicWave = function(real, imag){
  return { kind:'wave', imag: Array.from(imag || []) } };
Recorder.prototype.createOscillator = function(){
  return { type:'', frequency:{kind:'frequency',
             setValueAtTime(v){ freqs.push(v) }, exponentialRampToValueAtTime(){}},
           setPeriodicWave(){ nodes.push('pulse') },
           connect(){ nodes.push('oscillator') }, start(){}, stop(){} } };
Recorder.prototype.createBuffer = function(ch, len){
  return { getChannelData: () => new Float32Array(len) } };
Recorder.prototype.createBufferSource = function(){
  return { buffer:null, start(){}, stop(){},
    connect(t){ nodes.push(t && t.kind === 'lowpass' ? 'noise->lowpass' : 'noise->direct') } } };
Recorder.prototype.createBiquadFilter = function(){
  return { kind:'lowpass', type:'',
    frequency:{ setValueAtTime(){}, exponentialRampToValueAtTime(){} },
    connect(){ nodes.push('lowpass->out') } } };
Recorder.prototype.createGain = function(){
  return { gain:{ setValueAtTime(v){ played.push(v) },
                  exponentialRampToValueAtTime(){} },
    connect(t){ if (t && t.kind === 'frequency') nodes.push('lfo->frequency') } } };
globalThis.window = { AudioContext: Recorder };
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
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(30);
/* Five gems, standing on the lantern's ledge: the light comes on. */
me.gems = 5; me.x = lamp.x; me.y = lamp.y - 40; me.vy = 0;
nodes.length = 0; run(30);
console.log(JSON.stringify({ lampLit: lamp.lit, lampNodes: nodes.slice() }));
"""


def lamp_sfx_probe(script: str) -> str:
    """The page's own script, wrapped so the lantern's voice can be heard."""

    return LAMP_SFX_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: What the lantern gives back, and what it refuses (§5, C-1674).
#:
#: The adventure's shrine took payment at the ceiling and celebrated;
#: this lantern already guards itself with ``!lamp.lit``. That is the
#: half worth pinning: the template that got it right had nothing holding
#: it there. The lantern is lit for real, then stood on again with a full
#: purse, and both visits are recorded whole - gems, light, sentence,
#: sound, particles.
LAMP_SINK_PROBE = KEY_EVENT_JS + """
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
PROBE_KEYS_PLACEHOLDER
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function key(k){
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
let heard = [], thrown = 0;
const realSfx = sfx, realBurst = burst;
sfx = function(name){ heard.push(name); return realSfx.apply(null, arguments) };
burst = function(x, y, n){ thrown += (n || 0); return realBurst.apply(null, arguments) };
/* Off the title screen first: the course does not run until a key. */
key(' '); run(30);
function stand(gems){
  me.gems = gems; me.x = lamp.x; me.y = lamp.y - 40; me.vy = 0;
  /* A sentence from an earlier visit is not this visit's answer. */
  heard = []; thrown = 0; msgT = 0; msg = null;
  const gems0 = me.gems, lit0 = lamp.lit;
  run(30);
  return { gemsBefore: gems0, gemsAfter: me.gems, litBefore: lit0,
    litAfter: lamp.lit, said: typeof msg === 'string' ? msg : null,
    heard: heard.slice(), thrown: thrown };
}
const first = stand(LAMP_COST);
const again = stand(LAMP_COST * 2);
console.log(JSON.stringify({ cost: LAMP_COST, first: first, again: again }));
"""


def lamp_sink_probe(script: str) -> str:
    """The page's own script, wrapped so the lantern can be paid twice."""

    from sidra_ai.creation import probekeys

    return probekeys.with_probe_keys(
        LAMP_SINK_PROBE.replace("SCRIPT_PLACEHOLDER", script)
    )


#: The face, driven (§1, C-1348): run right and the eyes look right, run
#: left and they follow, jump and they lift, wait and they blink - once,
#: briefly. The reduced-motion run is the other half: the blink never
#: comes, because FRAME pins the face open.

#: The two roads, as driven (§3, C-1367). The page is really played three
#: ways: the auto-runner takes the low road to the flag and must never
#: board the shelf (soft = bypassable); a standing held jump from the
#: base's centre boards it and earns its gems (the lock opens to skill);
#: the same jump from the stretch's lowest platform falls short (the lock
#: is real). Direct state ops are the racing/guard probes' precedent.
ROUTE_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let CLOCK = 0;
globalThis.performance = { now: () => CLOCK };
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
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; CLOCK = (F++) * 16; fn(CLOCK) } }
function ev(type, k){
  const e = probeKey(k);
  (handlers[type] || []).forEach(fn => fn(e));
}
function onShelf(){ return me.ground &&
  SHELF.some(p => Math.abs(me.y - p.y) < 1 && me.x >= p.x - 2 && me.x <= p.x + p.w + 2) }
ev('keydown', ' '); ev('keyup', ' ');
run(4);
const facts0 = routeFacts();
/* (a) The low road: run right, jump where the floor runs out - the
   attract pilot's own rule - and reach the flag without the shelf. */
/* Capped inside the 60-second round: the (b)/(c) jumps below need live
   round time - past the buzzer the round wrapper intercepts step() and
   the world freezes (C-1349's mechanism, met here as a frozen probe). */
ev('keydown', 'ArrowRight');
let goal = false, boarded = false;
for (let i = 0; i < DRIVE_INPUT && !goal; i++) {
  if (me.ground && !plats.some(p => me.x + 30 > p.x - 6 && me.x + 30 < p.x + p.w + 6
      && p.y >= me.y - 1 && p.y < me.y + 60)) tryJump();
  run(1);
  if (onShelf()) boarded = true;
  if (state !== 'play') { goal = state === 'goal'; break }
}
ev('keyup', 'ArrowRight');
const lowGems = routeFacts().gems.slice();
/* (b) The high road: reset, stand on the base's centre, one held
   standing jump onto the shelf, then run and jump along it. */
ev('keydown', 'r'); ev('keyup', 'r'); run(2);
const base = routeFacts().base;
me.x = base.x + base.w / 2; me.y = base.y; me.vy = 0;
me.ground = true; me.coyote = 6; me.buffer = 0; me.held = false;
me.held = true; tryJump(); run(26); me.held = false;
const onFirst = onShelf();
if (onFirst) {
  ev('keydown', 'ArrowRight'); run(8); ev('keyup', 'ArrowRight');
  ev('keydown', 'ArrowLeft'); run(16); ev('keyup', 'ArrowLeft');
}
const highGems = routeFacts().gems.slice();
/* (c) The same jump from the stretch's lowest platform falls short. */
ev('keydown', 'r'); ev('keyup', 'r'); run(2);
const sy = routeFacts().shelf[0].y;
let low = null;
const lo = Math.floor(plats.length / 3), hi = Math.floor(plats.length * 2 / 3);
for (let i = lo; i <= hi; i++) { const pl = plats[i];
  if (Math.abs(pl.y - sy) < 1) continue;
  if (!low || pl.y > low.y) low = pl }
me.x = low.x + low.w / 2; me.y = low.y; me.vy = 0;
me.ground = true; me.coyote = 6; me.buffer = 0;
let minY = me.y;
me.held = true; tryJump();
for (let i = 0; i < 40; i++) { run(1); if (me.y < minY) minY = me.y }
me.held = false;
console.log(JSON.stringify({ facts0: facts0, goal: goal, boarded: boarded,
  lowGems: lowGems, onFirst: onFirst, highGems: highGems,
  lowY: low.y, baseY: facts0.base.y, shelfY: sy, minY: minY,
  shortBy: sy - minY }));
"""


#: The lantern's books (§5, C-1376): the low road alone - no shelf, no
#: skill lock - must hold at least LAMP_COST gems, or the lamp is a
#: price tag on an empty shelf. Read off the built course, not the
#: source: the seed has already decided every orb.
ECON_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = () => {};
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
globalThis.requestAnimationFrame = () => 1;
SCRIPT_PLACEHOLDER
console.log(JSON.stringify({
  low: orbs.filter(o => !o.shelf).length,
  shelf: orbs.filter(o => o.shelf).length,
  cost: LAMP_COST,
}));
"""


def econ_probe(script: str) -> str:
    """The page's own script, wrapped so the course's books can be read."""

    return ECON_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The books, met on the road (§5, C-1714). ``ECON_PROBE`` counts what the
#: seed placed; this walks the low road with the page's own one-rule pilot
#: and reports what the player is holding when the price is asked. The two
#: are different facts: six gems on a course whose lantern stands after
#: the fourth is a lantern nobody can light on the way past.
TAPSINK_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.document = { readyState: 'complete', createElement: () => nothing,
  querySelector: () => null,
  getElementById: () => ({ width: 720, height: 320, style: {},
    addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
PROBE_KEYS_PLACEHOLDER
SCRIPT_PLACEHOLDER
let F = 0;
function turn(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(type, k){ (handlers[type] || []).forEach(fn => fn(probeKey(k))) }
/* What the seed placed, before a step is taken - the fact ECON_PROBE
   reports, kept here so the two readings sit side by side. */
const placed = { low: orbs.filter(o => !o.shelf).length,
  shelf: orbs.filter(o => o.shelf).length,
  beforeLamp: orbs.filter(o => !o.shelf && o.x < lamp.x).length,
  afterLamp: orbs.filter(o => !o.shelf && o.x >= lamp.x).length };
ev('keydown', ' '); ev('keyup', ' '); turn(4);
ev('keydown', 'ArrowRight');
let goal = false, held = null, lit = false, nearest = Infinity, nearHeld = null;
for (let i = 0; i < DRIVE_INPUT; i++) {
  /* The attract pilot's own one rule, the same one ROUTE_PROBE drives. */
  if (me.ground && !plats.some(p => me.x + 30 > p.x - 6 && me.x + 30 < p.x + p.w + 6
      && p.y >= me.y - 1 && p.y < me.y + 60)) tryJump();
  /* The purse as it stands BEFORE the frame runs. The frame that reaches
     the lantern is also the frame that pays, so read afterwards this is
     the change and not the fare. */
  const purse = me.gems;
  const away = Math.abs(lamp.x - me.x);
  if (away < nearest) { nearest = away; nearHeld = purse }
  turn(1);
  if (!lit && lamp.lit) { lit = true; held = purse }
  if (state !== 'play') { goal = state === 'goal'; break }
}
ev('keyup', 'ArrowRight');
console.log(JSON.stringify({ cost: LAMP_COST, placed: placed,
  goal: goal, lit: lamp.lit, heldAtLamp: held, left: me.gems,
  nearestLamp: Math.round(nearest), heldNearLamp: nearHeld,
  gotLow: orbs.filter(o => o.got && !o.shelf).length,
  gotShelf: orbs.filter(o => o.got && o.shelf).length }));
"""


def tapsink_probe(script: str, *, drive: int = 4000) -> str:
    """The page's own script, wrapped so the fare can be met on the road."""

    from sidra_ai.creation import probekeys

    return probekeys.with_probe_keys(
        TAPSINK_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
            "DRIVE_INPUT", str(int(drive))
        )
    )


def route_probe(script: str, *, drive: int = 2400) -> str:
    """The page's own script, wrapped so both roads can be driven.

    ``drive`` caps the low-road walk in frames; pass 0 to only read the
    geometry (a harder course than the pilot's one rule can clear still
    has to carry the same seeded shelf).
    """

    return ROUTE_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "DRIVE_INPUT", str(int(drive))
    )

FACE_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
/* The blink is a fact about the wall clock (faceFacts reads
   performance.now itself), so this probe's clock ticks with the frames
   instead of being pinned to zero. */
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
  const e = probeKey(k);
  (handlers[type] || []).forEach(fn => fn(e));
}
ev('keydown', ' '); ev('keyup', ' ');
run(30);
ev('keydown', 'ArrowRight'); run(20);
const lookRight = faceFacts().look;
ev('keyup', 'ArrowRight');
ev('keydown', 'ArrowLeft'); run(20);
const lookLeft = faceFacts().look;
ev('keyup', 'ArrowLeft');
/* The rise lifts the gaze: read the frame after a landed jump fires. */
let upWhileRising = false;
ev('keydown', 'ArrowUp');
for (let i = 0; i < 12; i++) { run(1);
  if (me.vy < -1 && faceFacts().up) { upWhileRising = true; break } }
ev('keyup', 'ArrowUp');
/* Then stand still and count the blink. */
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
  lookRight: lookRight, lookLeft: lookLeft, upWhileRising: upWhileRising,
  blinkFrames: blinkFrames, longestBlink: longest,
}));
"""


def face_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the hero's face can be watched."""

    return FACE_PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "SCRIPT_PLACEHOLDER", script
    )


#: The message stays long enough to read (§4 増築, C-1395): the page's
#: own say() is driven with the page's own literals - a short one that
#: must show for exactly the old flat count (bit-compat), and the longest
#: one, whose frame count must reach 15 frames a character = the 4
#: characters-per-second Japanese subtitle standard.
SAY_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
let texts = [];
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy({
    fillText: (s) => { texts.push(String(s)) } }, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: () => true }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(type, k){
  const e = probeKey(k);
  (handlers[type] || []).forEach(fn => fn(e));
}
ev('keydown', ' '); ev('keyup', ' ');
run(300);
function countShown(text){
  say(text);
  let n = 0, guard = 0;
  while (msgT > 0 && guard++ < 3000) {
    texts = []; run(1);
    if (texts.indexOf(text) >= 0) n++;
  }
  return n }
const shortShown = countShown(SHORT_PLACEHOLDER);
const longShown = countShown(LONG_PLACEHOLDER);
console.log(JSON.stringify({ shortShown: shortShown, longShown: longShown }));
"""


def say_probe(script: str, *, short: str, long: str) -> str:
    """The page's own script, wrapped so the message's real display time
    can be counted for the page's own words."""

    return (
        SAY_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("SHORT_PLACEHOLDER", json.dumps(short, ensure_ascii=False))
        .replace("LONG_PLACEHOLDER", json.dumps(long, ensure_ascii=False))
    )


#: The camera's lead, driven (§27, C-1622). The hero is walked right
#: until the camera settles, then left, and where it sits on screen is
#: read back - the view ahead is what is left of the canvas past it.
CAMERA_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
/* The blink is a fact about the wall clock (faceFacts reads
   performance.now itself), so this probe's clock ticks with the frames
   instead of being pinned to zero. */
let CLOCK = 0;
globalThis.performance = { now: () => CLOCK };
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
const held = {};
function hold(k, on){ held[k] = on }
globalThis.__held = held;
function key(type, k){
  const e = probeKey(k);
  (handlers[type] || []).forEach(fn => fn(e));
}
key('keydown', ' '); key('keyup', ' ');
run(3);
/* The hero is held at a mid-level spot and only the FACING is changed, so
   what is measured is the camera's own behaviour rather than the level's
   pits and walls. Walking there blind runs off the end or falls in. */
const MID = Math.round(LW / 2);
let lastCam = cam, jumped = 0;
function settle(look, frames){
  for (let i = 0; i < frames; i++) {
    me.x = MID; me.look = look; me.y = 200; me.vy = 0;
    run(1);
    jumped = Math.max(jumped, Math.abs(cam - lastCam));
    lastCam = cam;
  }
  return me.x - cam;
}
const rightScreenX = settle(1, 200);
/* Now turn around. The single-frame camera move across the turn is what
   §27 事実 2 says a locked camera gets wrong. */
jumped = 0;
const leftScreenX = settle(-1, 200);
const turnJump = jumped;
console.log(JSON.stringify({
  W: W, lock: 260,
  rightScreenX: Math.round(rightScreenX * 100) / 100,
  leftScreenX: Math.round(leftScreenX * 100) / 100,
  viewAheadRight: Math.round((W - rightScreenX) * 100) / 100,
  viewAheadLeft: Math.round(leftScreenX * 100) / 100,
  maxJump: Math.round(turnJump * 100) / 100,
  onScreen: rightScreenX > 0 && rightScreenX < W
    && leftScreenX > 0 && leftScreenX < W,
  camLook: CAM_LOOK, camEase: CAM_EASE
}));
"""


def camera_probe(script: str) -> str:
    """The page's own script, wrapped so the camera's lead can be measured."""

    return CAMERA_PROBE.replace("SCRIPT_PLACEHOLDER", script)



TRAIL_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
/* A recording context, because a number in platFacts() is not paint
   (the trap C-1615 and C-1618 each fell into once). globalAlpha is
   tracked across save/restore, so an afterimage cannot be counted at the
   hero's own opacity. */
let ALPHA = 1, RECTS = [];
const STACK = [];
const rec = new Proxy(function(){}, {
  get: (t, k) => {
    if (k === 'globalAlpha') return ALPHA;
    if (k === 'save') return () => { STACK.push(ALPHA) };
    if (k === 'restore') return () => { ALPHA = STACK.length ? STACK.pop() : 1 };
    if (k === 'fillRect') return (x, y, w, h) => { RECTS.push({ x: x, w: w, h: h, a: ALPHA }) };
    if (k === Symbol.toPrimitive) return () => 0;
    return nothing },
  set: (t, k, v) => { if (k === 'globalAlpha') { ALPHA = v } return true },
  apply: () => nothing });
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => rec }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function ev(k){ return probeKey(k) }
function down(k){ (handlers.keydown || []).forEach(fn => fn(ev(k))) }
function up(k){ (handlers.keyup || []).forEach(fn => fn(ev(k))) }
/* Past the briefing, then hold right: the run is the thing that streaks. */
down(' '); up(' ');
run(4);
down('ArrowRight');
run(40);
/* One recorded frame, so what is counted is what was drawn. The hero's
   own body is 14x12 at full opacity and the record's ghost is one rect;
   ten faint ones is the streak. */
RECTS = [];
run(1);
const painted = RECTS.filter(r => Math.abs(r.w - 14) < 1e-9
  && Math.abs(r.h - 12) < 1e-9 && r.a < 0.999);
const paintedMax = painted.length ? Math.max.apply(null, painted.map(r => r.a)) : 0;
const running = platFacts();
const runSpan = running.trail.length
  ? running.x - Math.min.apply(null, running.trail) : 0;
const behind = running.trail.every(x => x <= running.x + 0.001);
/* On the flat the height never changes, so this is the control the fall
   is measured against. */
const walkSpanY = running.trailY.length
  ? Math.max.apply(null, running.trailY) - Math.min.apply(null, running.trailY) : 0;
/* Let go and stand: the streak has to drain, or the length is decoration
   rather than speed. */
up('ArrowRight');
/* Running right can walk off a ledge, and a falling hero is still moving.
   Let the fall land first, so what is measured is a hero standing still. */
run(80);
const still = platFacts();
let drained = null;
for (let i = 0; i < 30 && drained === null; i++) { run(1);
  if (platFacts().trail.length === 0) drained = i }
/* And one recorded frame after it has stopped: nothing faint is left. */
RECTS = [];
run(1);
const stillPainted = RECTS.filter(r => Math.abs(r.w - 14) < 1e-9
  && Math.abs(r.h - 12) < 1e-9 && r.a < 0.999).length;
/* A fall accelerates - the one place this template's speed varies - so
   the streak has to stretch with it. */
me.y = 40; me.vy = 0; me.ground = false; me.coyote = 0;
run(14);
const falling = platFacts();
const fallSpanY = falling.trailY.length
  ? Math.max.apply(null, falling.trailY) - Math.min.apply(null, falling.trailY) : 0;
console.log(JSON.stringify({ painted: painted.length, paintedMax: paintedMax,
  stillPainted: stillPainted,
  still: still.ground, stillTrail: still.trail.length,
  full: running.trail.length, behind: behind,
  runSpan: runSpan, walkSpanY: walkSpanY, fallSpanY: fallSpanY,
  drained: drained, fallFull: falling.trail.length }));
"""


def trail_probe(script: str, *, reduced: bool = False) -> str:
    """Run, stop, then fall - the three readings §1's streak has to make."""

    return TRAIL_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The runner's ear (§2 増築, C-1633). Two gems are placed on opposite
#: sides of the SCREEN and picked up by walking the hero onto them, and
#: the panner values are read off the audio graph the page really built.
#: One more is placed off-camera on purpose: this template scrolls, so a
#: world x would hand ``sfx`` a number outside 0..1 and pin the sound to
#: an edge - the reading proves the camera is in the sum.
PAN_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  /* Not a no-op here: the loop below breaks on it (C-1654 第 3 陣). */
  e.stopImmediatePropagation = function(){ stopped = true };
  for (const fn of (handlers[type] || [])) { fn(e); if (stopped) break }
}
ev('keydown', ' '); ev('keyup', ' ');
run(3);
/* Everything so far - the start - is positionless. */
const before = pans.length;
const calls = [];
const realSfx = sfx;
sfx = function(name, pitch, at){ const was = pans.length;
  const out = realSfx.call(this, name, pitch, at);
  calls.push({ name: String(name), pan: pans.length > was ? pans[pans.length - 1] : null });
  return out };
/* A gem is picked up by standing on it - the page's test is a box 14px
   around the hero - so the hero can never be far from it. What puts the
   two pickups on opposite sides of the SCREEN is the camera's own clamp:
   at the start of the level it cannot scroll left of 0, and at the end it
   cannot scroll past LW-W, so the hero rides to the edge of the picture. */
function take(worldX){
  orbs.length = 0;
  me.x = worldX;
  cam = camAim();
  orbs.push({ x: worldX, y: me.y - 10, got: false });
  const at = calls.length;
  run(1);
  return { calls: calls.slice(at).filter(c => c.name === 'gem'),
    screenX: worldX - cam, worldX: worldX, cam: cam };
}
const left = take(60);
const right = take(LW - 10);
const W_ = 720;
function want(x){ return Math.max(-0.8, Math.min(0.8, (x / W_ * 2 - 1) * 0.8)) }
const expected = [want(left.screenX), want(right.screenX)];
/* What the same two pickups would sound like if the camera were left out
   of the sum: the far one pins to the edge and stops meaning anything. */
const ifWorld = [want(left.worldX), want(right.worldX)];
/* Every panner the staged frames built, not the first two: a stray sound
   that quietly acquired a place has to break the count. */
console.log(JSON.stringify({ before: before, pans: pans,
  names: calls.map(c => c.name + (c.pan === null ? '' : '@')),
  expected: expected, ifWorld: ifWorld,
  left: left, right: right }));
"""


def pan_probe(script: str) -> str:
    """The page's own script, wrapped so a pickup's stereo place can be read."""

    return PAN_PROBE.replace("SCRIPT_PLACEHOLDER", script)

__all__ = [
    "PAN_PROBE",
    "pan_probe",
    "TRAIL_PROBE",
    "trail_probe",
    "CAMERA_PROBE",
    "camera_probe",
    "SAY_PROBE",
    "say_probe",
    "PLATFORMER_DIFFICULTY",
    "ECON_PROBE",
    "econ_probe",
    "TAPSINK_PROBE",
    "tapsink_probe",
    "FACE_PROBE",
    "LAMP_SFX_PROBE",
    "SQUASH_PROBE",
    "face_probe",
    "lamp_sfx_probe",
    "squash_probe",
    "PLATFORMER_HOW",
    "PLATFORMER_SCRIPT",
    "PLATFORMER_TITLE",
    "PLATFORMER_WORDS",
    "BUFFER_PROBE",
    "buffer_probe",
    "PROBE",
    "probe_source",
]
