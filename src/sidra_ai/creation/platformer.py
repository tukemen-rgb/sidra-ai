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
setPal(PLAT_PAL_TOKEN);
/* seeded LCG: same request, same course - the regeneration promise. */
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
let plats,orbs,lamp,flag,LW,me,state,respawns,msg,msgT;
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
  const mid=plats[Math.floor(plats.length/2)];
  lamp={x:mid.x+mid.w/2,y:mid.y,lit:false};
  /* the lantern's platform keeps no gem: two pickups in one spot would
     read as one */
  orbs=orbs.filter(o=>Math.abs(o.x-lamp.x)>1)}
function reset(){rs=(SEED>>>0)||1;build();state='play';respawns=0;
  me={x:60,y:230,vy:0,ground:false,coyote:0,buffer:0,held:false,gems:0,
    cpX:60,cpY:262,sq:1};
  say('足場を渡って、旗まで。')}
function say(t){msg=t;msgT=150}
const keys={};
function K(k){return keys[k]}
function tryJump(){if(state!=='play')return;
  /* coyote>0 covers both "standing" and "just walked off": the window is
     refilled every grounded frame and spent one frame at a time in the air,
     so a late edge press lands and a mid-fall press does not - not right
     away. A press held while airborne is kept for BUFFER frames instead of
     dropped, and fires on the landing frame (§12). */
  if(me.coyote>0){me.vy=JUMP;me.coyote=0;me.ground=false;sfx('catch');
    /* Squash & stretch (§1, C-1332): the take-off stretches the body
       tall; under reduced motion the silhouette never changes. */
    if(!REDUCED)me.sq=1.25}
  else{me.buffer=BUFFER}}
function cutJump(){me.held=false;me.buffer=0;if(me.vy<CUT)me.vy=CUT}
addEventListener('keydown',e=>{keys[e.key]=true;
  if(e.key==='ArrowUp'||e.code==='Space'){e.preventDefault();
    if(!me.held){me.held=true;tryJump()}}
  if(e.key==='r'||e.key==='R')reset()});
addEventListener('keyup',e=>{keys[e.key]=false;
  if(e.key==='ArrowUp'||e.code==='Space')cutJump()});
cv.addEventListener('pointerdown',()=>{
  if(state==='play'){if(!me.held){me.held=true;tryJump()}}else{reset()}});
cv.addEventListener('pointerup',()=>{cutJump()});
function step(){const now=performance.now();
  if(state==='play'){
    if(K('ArrowLeft')){me.x=Math.max(10,me.x-RUN)}
    if(K('ArrowRight')){me.x=Math.min(LW-10,me.x+RUN)}
    const vBefore=me.vy;
    me.vy=Math.min(8,me.vy+GRAV);me.y+=me.vy;
    /* one-way platforms: solid only when the feet cross the top going down,
       so a jump from below never bonks and the arc stays the player's */
    let on=false;
    if(me.vy>=0){for(const p of plats){
      if(me.x>p.x-6&&me.x<p.x+p.w+6&&me.y>=p.y&&me.y-me.vy<=p.y+0.001){
        me.y=p.y;me.vy=0;on=true;break}}}
    if(on){
      if(!me.ground){sfx('step');
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
      o.got=true;me.gems++;sfx('gem');burst(o.x,o.y,10,'ACCENT_JUICE');
      say(me.gems>=LAMP_COST&&!lamp.lit
        ?'宝石 '+me.gems+' 個。灯籠を点けられる。':'宝石 '+me.gems+' 個。')}});
    /* The sink (§5): gems light the lantern that moves the respawn point.
       A collectible that buys insurance is a reason to detour for it. */
    if(!lamp.lit&&Math.abs(lamp.x-me.x)<18&&Math.abs(lamp.y-me.y)<26){
      if(me.gems>=LAMP_COST){me.gems-=LAMP_COST;lamp.lit=true;
        me.cpX=lamp.x;me.cpY=lamp.y;sfx('key');
        burst(lamp.x,lamp.y-18,16,'ALERT_JUICE');
        say('灯籠がともった。落ちてもここから。')}
      else if(msgT<=0){say('灯籠は宝石 '+LAMP_COST+' 個で点く（いま '+me.gems+' 個）。')}}
    if(Math.abs(flag.x-me.x)<16&&me.y>flag.y-30&&me.y<=flag.y+2){
      state='goal';winBeat(flag.x,flag.y-30)}
    /* Falling costs a walk back, never the run: respawn at the last lit
       lantern (or the start), no game over. */
    if(me.y>H+40){respawns++;me.x=me.cpX;me.y=me.cpY-6;me.vy=0;me.coyote=0;
      sfx('hurt');shake(4);hitstop(4);
      say(lamp.lit?'灯籠まで戻された。':'足場のはじめに戻された。')}
    /* The trail of the run that set the record (§11, C-1330): the course
       x is the progress, the height is what is remembered there. Sampled
       after the physics has settled the frame, so a respawn records the
       lantern, not the pit. Walking back overwrites a bucket - the trail
       means "where you were, here, last time". */
    ghostSample(me.x,me.y)}
  draw(now);requestAnimationFrame(step)}
function seg(){return me.x<LW*0.34?0:me.x<LW*0.72?1:2}
function draw(now){
  /* 序盤 -> 中盤 -> ゴール前: progress picks the accent hue, and the goal
     stretch keeps the brightest値 for last (§7 観察 5-6). */
  setScene(seg());
  cx.fillStyle=scenePaint('BG_TOKEN');cx.fillRect(0,0,W,H);
  const cam=Math.max(0,Math.min(LW-W,me.x-260));
  /* distance is contrast, not colour (§7 観察 7): a faint far ridge on a
     slower scroll */
  cx.globalAlpha=0.22;cx.fillStyle=scenePaint('RAISED_TOKEN');
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
    cx.strokeStyle='#dfe7f5';cx.strokeRect(lx-7.5,lamp.y-40.5,15,17);
    /* A number written on the lamp, so it is ink like every other
       word on the page - white on a light theme is not readable (C-1131). */
    if(!lamp.lit){cx.fillStyle='INK_TOKEN';cx.font='11px ui-monospace,monospace';
      cx.fillText(String(LAMP_COST),lx-3,lamp.y-28)}}
  const fx=flag.x-cam;
  if(fx>-40&&fx<W+40){
    cx.fillStyle='#dfe7f5';cx.fillRect(fx-1,flag.y-46,3,46);
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
  /* Feet-anchored squash & stretch: height scales with sq, width the
     other way, so the volume reads constant and the feet never float. */
  const sqh=12*me.sq,sqw=14*(2-me.sq),sqt=me.y-6-sqh;
  cx.fillStyle='CYAN_TOKEN';cx.fillRect(px-sqw/2,sqt,sqw,sqh);
  cx.fillRect(px-3,sqt-6,6,6);
  /* the gait is position-driven, so it only moves when the player does */
  const g2=me.ground?Math.sin(me.x/5)*4:3;
  cx.strokeStyle='CYAN_TOKEN';cx.lineWidth=2;
  cx.beginPath();cx.moveTo(px-3,me.y-6);cx.lineTo(px-3-g2,me.y);cx.stroke();
  cx.beginPath();cx.moveTo(px+3,me.y-6);cx.lineTo(px+3+g2,me.y);cx.stroke();
  cx.lineWidth=1;
  cx.fillStyle='INK_TOKEN';cx.font='13px ui-monospace,monospace';
  cx.fillText('宝石 '+me.gems+' / '+LAMP_COST+(lamp.lit?'  灯籠 点':'')
    +'  落下 '+respawns,40,20);
  if(msgT>0){msgT--;cx.fillStyle='SCRIM_TOKEN'+'d9';cx.fillRect(20,H-34,W-40,26);
    cx.fillStyle='INK_TOKEN';cx.fillText(msg,30,H-16)}
  if(state==='goal'){cx.fillStyle='SCRIM_TOKEN'+'d0';cx.fillRect(0,0,W,H);
    cx.fillStyle='INK_TOKEN';cx.font='20px ui-monospace,monospace';
    const a='灯りは旗までとどいた。';
    cx.fillText(a,W/2-a.length*10,H/2-8);
    cx.font='13px ui-monospace,monospace';
    const b='宝石 '+me.gems+' 個 / 落下 '+respawns+' 回 / R かタップでもう一度';
    cx.fillText(b,W/2-b.length*6.5,H/2+18)}}
function platFacts(){return{x:me.x,y:me.y,vy:me.vy,ground:me.ground,
  squash:me.sq,
  coyote:me.coyote,window:COYOTE,buffer:me.buffer,bufferWindow:BUFFER,
  gems:me.gems,respawns:respawns,
  lit:lamp.lit,cpX:me.cpX,state:state,lampX:lamp.x,lampY:lamp.y,
  flagX:flag.x,flagY:flag.y,world:LW}}
reset();step();
"""

#: The buffered jump, played (C-1310): pressed and held a few frames before
#: landing it fires on the landing frame; released before landing it is
#: discarded - and a press in open air still never jumps on the spot.
BUFFER_PROBE = """
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
function ev(key){ return { key: key, code: key === ' ' ? 'Space' : key,
  preventDefault(){}, stopImmediatePropagation(){} } }
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
PROBE = """
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
function ev(key){ return { key: key, code: key === ' ' ? 'Space' : key,
  preventDefault(){}, stopImmediatePropagation(){} } }
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
/* The flag ends the run in a completed state, not another screen of play. */
me.x = flag.x; me.y = flag.y - 40; me.vy = 0; run(40);
const end = platFacts();
const palette = sceneFacts();
console.log(JSON.stringify({
  scenes: palette.scenes,
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


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the course can be played in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: Squash & stretch, watched frame by frame (§1, C-1332): one real jump.
#: The body must stretch past 1 while rising, squash below 1 on the exact
#: landing frame, settle back to rest within half a second - and under
#: reduced motion every sampled frame must read exactly 1, because the
#: silhouette is the one thing that run promises never changes.
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
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function kd(k){ (handlers.keydown || []).forEach(fn => fn({ key: k,
  code: k === ' ' ? 'Space' : k, preventDefault(){}, stopImmediatePropagation(){} })) }
function ku(k){ (handlers.keyup || []).forEach(fn => fn({ key: k,
  code: k === ' ' ? 'Space' : k, preventDefault(){}, stopImmediatePropagation(){} })) }
kd(' '); ku(' ');
run(10);
const restSq = platFacts().squash;
/* One full jump, held to the top, sampled every frame of the arc. */
kd(' ');
let riseMax = 0, guard = 0, landSq = null, wasAir = false;
while (guard++ < 400) {
  run(1);
  const f = platFacts();
  if (!f.ground) { wasAir = true; riseMax = Math.max(riseMax, f.squash) }
  if (wasAir && f.ground) { landSq = f.squash; break }
}
ku(' ');
/* Half a second later the body is a body again. */
run(30);
const settled = platFacts().squash;
/* And the whole arc again with nothing pressed: standing still, the
   silhouette must not breathe on its own. */
let idleMax = 0;
for (let i = 0; i < 40; i++) { run(1);
  idleMax = Math.max(idleMax, Math.abs(platFacts().squash - 1)) }
console.log(JSON.stringify({
  restSq: restSq, riseMax: riseMax, landSq: landSq,
  settled: settled, idleMax: idleMax,
}));
"""


def squash_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so one jump's shape can be watched."""

    return SQUASH_PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "SCRIPT_PLACEHOLDER", script
    )


__all__ = [
    "PLATFORMER_DIFFICULTY",
    "SQUASH_PROBE",
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
