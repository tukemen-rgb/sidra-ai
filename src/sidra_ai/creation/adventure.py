"""The top-down action-adventure template - the third playable rule set.

Asked for with 「ゼルダの伝説 不思議なぼうし作って」 and a video of what that
should feel like: a tile world seen from above, a small hero with a hat, a
sword that cuts bushes, enemies, torches in a cave, a key and a treasure.
The video itself was an *original* game made by people who loved Minish Cap,
and that is exactly the deal this template offers: the genre, with SIDRA's
own hero and world, never Nintendo's names or art - ``games.generate_game``
swaps a trademarked title for this template's own and says so.

Same contract as the fishing and catch templates, because it is loaded by
the same machinery: one inline script, no network, tokens substituted by
``generate_game`` (``SPEED_TOKEN`` is enemy speed, ``BAND_TOKEN`` enemy
count, ``SEED_TOKEN`` the request-derived layout seed), the animation
preamble's ``REDUCED``/``ease``/``FRAME`` respected - the torch flicker and
particles freeze under reduced motion while the game stays playable.

Three rooms, because an adventure is *going somewhere*: a forest with an NPC
who says what to do, a cave where the enemies guard the key, an altar where
the key opens the chest. The layout is seeded from the request, so 「森の
冒険を作って」 and 「湖の冒険を作って」 are different worlds and the same
request tomorrow is the same world - the regeneration promise every SIDRA
generator keeps.
"""

from __future__ import annotations

from sidra_ai.creation.probekeys import KEY_EVENT_JS, with_probe_keys

import json

#: Words that pick this template. 「ゼルダ」 lands here so the request in the
#: directive routes at all; what happens to the *name* is the title guard's
#: job, not the router's.
ADVENTURE_WORDS: tuple[str, ...] = (
    "ゼルダ",
    "冒険",
    "アドベンチャー",
    "探索",
    "ダンジョン",
    "勇者",
    "見下ろし",
    "adventure",
    "zelda",
)

#: (enemy speed px/frame, enemies per room). The numbers a request's 難しく
#: actually moves, same shape as the other templates.
ADVENTURE_DIFFICULTY: dict[str, tuple[float, float]] = {
    "easy": (0.5, 2),
    "normal": (0.8, 3),
    "hard": (1.2, 4),
}

ADVENTURE_TITLE = "小さな帽子の冒険"
ADVENTURE_HOW = (
    "矢印キー / WASD で移動、SPACE かタップで剣。草を刈り、洞窟の敵から鍵を取り、"
    "祭壇の宝箱を開ける。やられたら R でやり直し。M で消音。"
)

#: The whole game. Rendered into the shared page shell; ``sprite()`` and the
#: animation preamble are prepended by ``generate_game`` like every template.
ADVENTURE_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const ESPEED=SPEED_TOKEN,ECOUNT=BAND_TOKEN,SEED=SEED_TOKEN;
const TILE=32,GW=20,GH=9,OX=40,OY=16;
setPal(ADV_PAL_TOKEN);
/* HUD contract (§4 WCAG 1.4.3, C-1334): draw() paints the HUD through
   these constants and hudFacts() reports them, so the metric can blend
   the plate over every measured sky the way the canvas does. The plate
   is the untinted theme surface at 0.7: the brightest final act was
   sinking the themed ink to ~3:1 here too (C-1329's fix, more templates). */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A}}
/* seeded LCG: the layout is a promise (same request, same world), and the
   enemies keep drawing from it so a run is reproducible too */
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
/* The knowledge key (§3, C-1340): a lock whose key is a fact, not an
   item. The stone in the forest tells a seeded order; knocking the cave's
   three marks in that order breaks the seal on the key without a single
   fight - the soft route around the hard one (enemies still drop it the
   regular way). Its own stream, so the layout every earlier seed promised
   does not move by one rand() call. */
let ks=((SEED^1234567)>>>0)||1;
function krand(){ks=(ks*48271)%2147483647;return ks/2147483647}
const KMARKS=['月','星','日'];
const KORDER=(()=>{const o=[0,1,2];for(let i=2;i>0;i--){
  const j=Math.floor(krand()*(i+1));const t=o[i];o[i]=o[j];o[j]=t}return o})();
let kprog=0,ksolved=false;
function knowFacts(){return {progress:kprog,solved:ksolved}}
const NAMES=['森のはずれ','ひかり苔の洞窟','風の祭壇'];
let rooms=[],enemies=[],room=0,msg='',msgT=0,guard=null;
let hero={x:0,y:0,dir:2,hp:3,gems:0,key:false,swing:0,inv:0,sq:1};
let state='play';let keyDrop=null;let FIRSTCUT=true;let PITY=0;
/* What took the hearts, kept apart because the two are different
   mistakes (C-1425): a roamer is something that closed the distance,
   the guardian is a telegraphed blow that landed anyway. Counting
   only - nothing here is read back by the game itself. */
let hurtRoam=0,hurtGuard=0;
function empty(){const m=[];for(let y=0;y<GH;y++){const r=[];
  for(let x=0;x<GW;x++){r.push(x===0||y===0||x===GW-1||y===GH-1?1:0)}m.push(r)}return m}
function carve(m,code,n){let put=0;while(put<n){const x=2+Math.floor(rand()*(GW-4)),
  y=2+Math.floor(rand()*(GH-4));if(m[y][x]===0){m[y][x]=code;put++}}}
function pond(m){const px=4+Math.floor(rand()*(GW-10)),py=2+Math.floor(rand()*(GH-6));
  for(let y=py;y<py+2;y++){for(let x=px;x<px+3;x++){if(m[y][x]===0){m[y][x]=3}}}}
function build(){
  const forest=empty();carve(forest,2,14);pond(forest);forest[3][3]=8;forest[4][GW-1]=5;
  /* One tuft of grass right where the hero wakes, whatever the seed did
     (§8 事実 5). carve() and pond() place by luck, so on some seeds the
     first swing hit nothing at all and the opening had no answer. */
  forest[4][3]=2;
  /* the sink: somewhere to spend gems, on the way out of the first room */
  forest[6][6]=9;
  /* the stone that knows the order (§3, C-1340) */
  forest[2][6]=12;
  const cave=empty();carve(cave,1,10);cave[0][6]=4;cave[0][13]=4;
  cave[4][0]=6;cave[4][GW-1]=5;
  /* the three marks the stone speaks of, placed by hand so carve()
     cannot bury one */
  cave[6][4]=13;cave[6][9]=14;cave[6][14]=15;
  /* the branch (knowledge base §3): a door nobody has to open, and a
     reward that is only worth it if you spent gems on grass first. The
     alcove is walled by hand so carve() cannot open a way around it. */
  cave[2][16]=10;cave[2][17]=11;
  cave[1][16]=1;cave[1][17]=1;cave[3][16]=1;cave[3][17]=1;cave[2][18]=1;
  const altar=empty();carve(altar,1,6);altar[4][0]=6;altar[4][10]=7;
  /* The guardian's floor: an arena carve() cannot wall shut, to the right
     of the chest, so the fight has room to read (§6 観察 1 - scale needs
     space around the small thing for contrast). */
  for(let y=2;y<7;y++){for(let x=12;x<18;x++){altar[y][x]=0}}
  rooms=[forest,cave,altar];
  /* The guardian (§3: the boss behind the boss key; §6: its grammar).
     Wakes when the room is entered; strides slowly - weight is stride
     (観察 2) - telegraphs with a held flash beat, then charges. Half
     health is phase 2: the same fight, re-accelerated (観察 3). */
  guard={x:OX+15*TILE,y:OY+4*TILE+16,hp:6,max:6,alive:true,
    mode:'stride',wind:0,chg:0,dx:0,dy:0,inv:0,t:70,step:0,hurt:0,smoke:0};
  enemies=[[],[],[]];
  for(let i=0;i<ECOUNT;i++){enemies[1].push(spawn(1))}
  for(let i=0;i<Math.max(1,ECOUNT-1);i++){enemies[2].push(spawn(2))}
}
function spawn(r){let x,y;do{x=2+Math.floor(rand()*(GW-4));
  y=2+Math.floor(rand()*(GH-4))}while(rooms[r][y][x]!==0||(r===2&&x>7&&x<13)
  /* never beside the entrance: the chase radius is 4 tiles, so a spawn
     next to the door bites the hero before the room is even visible */
  ||Math.abs(x-1)+Math.abs(y-4)<5);
  return {x:OX+x*TILE+8,y:OY+y*TILE+8,dx:0,dy:0,t:0,alive:true}}
/* How many hearts the shrine can build up to (§5, C-1674). Named, so the
   ceiling can be read where payment is taken and not only where the sum
   is capped. */
const HP_CAP=5;
function reset(){rs=(SEED>>>0)||1;build();room=0;keyDrop=null;state='play';FIRSTCUT=true;PITY=0;
  kprog=0;ksolved=false;hurtRoam=0;hurtGuard=0;
  hero={x:OX+2*TILE,y:OY+4*TILE,dir:2,hp:3,maxhp:3,gems:0,key:false,
    charm:false,swing:0,inv:0,sq:1};
  say('ぼうしの勇者、めざめる。')}
/* Long enough to READ (§4 増築, C-1395): the Japanese subtitle standard
   is 4 characters per second, and a flat 140 frames pushed the 22-char
   door hint out at 9.4/s. Fifteen frames a character IS 4/s at 60fps;
   the old 140 stays as the floor, so anything nine characters or under
   is bit-identical to what it always was. */
function say(t){msg=t;msgT=Math.max(140,Math.round(t.length*15))}
/* The face, as a fact (§1, C-1351): which way the hero faces, whether the
   eyes are visible at all - facing up is the back of the head, and a back
   has no eyes to draw - and whether this frame is the blink. Under
   reduced motion FRAME is pinned to 0, so the eyes never shut there. */
function faceFacts(){return {dir:hero.dir,shown:hero.dir!==0,
  blink:FRAME(40,6,performance.now())===1}}
function tileAt(px,py){const x=Math.floor((px-OX)/TILE),y=Math.floor((py-OY)/TILE);
  if(x<0||y<0||x>=GW||y>=GH)return 1;return rooms[room][y][x]}
function solid(px,py){const t=tileAt(px,py);
  return t===1||t===2||t===3||t===4||t===7||t===8||t===9||t===10||
    t===12||t===13||t===14||t===15}
const keys={};
addEventListener('keydown',e=>{keys[e.key.toLowerCase()]=true;
  if(!keyInForm(e)&&e.code==='Space'){e.preventDefault();swing()}
  if(e.key==='r'||e.key==='R'){if(state!=='play')reset()}});
addEventListener('keyup',e=>{keys[e.key.toLowerCase()]=false});
cv.addEventListener('pointerdown',()=>{if(state==='play'){swing()}else{reset()}});
function swing(){if(state!=='play')return;
  /* A press during the swing is kept, not dropped (§12, C-1311): one
     queued blow, fired the frame the arm is free. Mashing becomes a
     steady fastest-possible rhythm instead of a lottery. */
  if(hero.swing>0){hero.queued=true;return}
  hero.swing=10;
  const fx=hero.x+[0,16,0,-16][hero.dir]*1.25,fy=hero.y+[-16,0,16,0][hero.dir]*1.25;
  /* §2 増築 (C-1394, C-1630): the blade's own x, not the hero's - a swing
     to the left is heard on the left. The value was already being computed
     one line down for the hit test; it just never reached the ear. */
  sfx('sword',1,fx/cv.width);
  const tx=Math.floor((fx-OX)/TILE),ty=Math.floor((fy-OY)/TILE);
  if(ty>=0&&ty<GH&&tx>=0&&tx<GW){
    const t=rooms[room][ty][tx];
    if(t===2){rooms[room][ty][tx]=0;sfx('cut',1,(OX+tx*TILE+TILE/2)/cv.width);
      burst(OX+tx*TILE+TILE/2,OY+ty*TILE+TILE/2,10,'ACCENT_JUICE');
      /* The first cut always pays. After that the odds are the odds,
         with a floor (§5, C-1376): the world holds 14 tufts and nothing
         regrows, so an unlucky tail could close every sink - about one
         run in twenty-nine used to end below the shrine's 3. Two misses
         in a row make the third cut pay for certain, which puts the
         worst case at 1+4=5 gems: the shrine's 3 with the door's 2 to
         spare, while the expected run feels the same odds as before. */
      if(FIRSTCUT||PITY>=2||rand()<0.34){FIRSTCUT=false;PITY=0;
        hero.gems++;say('草のかげに宝石があった。');
      sfx('gem',1,(OX+tx*TILE+TILE/2)/cv.width);
        burst(OX+tx*TILE+TILE/2,OY+ty*TILE+TILE/2,14,'ALERT_JUICE')}
      else{PITY++}}
    /* The boss stands behind the boss key (§3): the key alone is only half
       the lock while the guardian is on its feet. */
    if(t===7){if(!hero.key){say('鍵がかかっている。洞窟の敵が持っているらしい。');sfx('clash')}
      else if(guard&&guard.alive){say('番人が生きている限り、宝箱は開かない。');sfx('clash')}
      else{state='win';winBeat(hero.x,hero.y)}}
    if(t===8){say('「東の洞窟の敵が鍵を守っている。祭壇の宝を頼む。」');sfx('step')}
    /* The sink (§5): gems were a tap with no outlet, so cutting grass paid
       in a number. Three of them buy a heart, which is what makes the
       grass worth cutting. */
    if(t===9){
      /* The ceiling refuses payment (§5, C-1674). Math.min() used to
         saturate in silence: at five hearts the shrine still took three
         gems, still said they had bought a heart, still rang powerUp.
         Nine of the village's fifteen gems could vanish that way - and
         the optional door costs two, so a player could be talked out of
         the branch by a success sound. A sink that returns nothing is
         not a sink. */
      if(hero.maxhp>=HP_CAP){say('祠は満ち足りている。ハートはもう増えない。');sfx('clash')}
      else if(hero.gems>=3){hero.gems-=3;hero.maxhp=hero.maxhp+1;
        /* A bigger heart is a power, not a pickup (§2, C-1346). */
        hero.hp=hero.maxhp;say('祠が宝石を受け取った。ハートが増えた。');sfx('powerup');
        burst(OX+tx*TILE+TILE/2,OY+ty*TILE+TILE/2,18,'ALERT_JUICE')}
      else{say('祠は宝石を 3 個ほしがっている（いま '+hero.gems+' 個）。');sfx('clash')}}
    /* The optional door (§3): the run is winnable without ever opening it. */
    if(t===10){if(hero.gems>=2){hero.gems-=2;rooms[room][ty][tx]=0;
        say('わき道が開いた。');sfx('key')}
      else{say('宝石 2 個で開きそうだ（いま '+hero.gems+' 個）。');sfx('clash')}}
    /* The knowledge key (§3, C-1340): the stone SAYS the order - the
       knowledge lives in the world, not in a facts function - and the
       marks answer to it. */
    if(t===12){say('石碑「'+KORDER.map(i=>KMARKS[i]).join('→')+
      ' の順に、洞窟の印を叩け」');sfx('step')}
    if(t===13||t===14||t===15){knock(t-13,tx,ty)}}
  enemies[room].forEach(en=>{if(!en.alive)return;
    if(Math.hypot(en.x-fx,en.y-fy)<22){en.alive=false;sfx('hurt',1,en.x/cv.width);
      shake(6);hitstop(3);burst(en.x,en.y,16,'ALERT_JUICE');
      if(room===1&&enemies[1].every(e=>!e.alive)){keyDrop={x:en.x,y:en.y}}}});
  /* The guardian takes a blade with weight: thirty frames of armour after
     each hit, so mashing lands one blow, not six. Half health turns the
     page to phase 2 (§6 観察 3). */
  if(room===2&&guard&&guard.alive&&guard.inv<=0&&Math.hypot(guard.x-fx,guard.y-fy)<30){
    /* A blow on a boss reads in three beats (§6 観察 2, C-1343): flash,
       smoke that stays, silhouette back out of it - kaiju's own numbers. */
    guard.hp--;guard.inv=30;guard.hurt=8;guard.smoke=34;
    sfx('hurt',1,guard.x/cv.width);shake(8);hitstop(4);
    burst(guard.x,guard.y,16,'ALERT_JUICE');
    guard.x+=[0,12,0,-12][hero.dir];guard.y+=[-12,0,12,0][hero.dir];
    if(guard.hp<=0){guard.alive=false;sfx('win',1,guard.x/cv.width);shake(12);hitstop(6);
      burst(guard.x,guard.y,32,'ALERT_JUICE');
      say('番人は崩れ落ちた。祭壇が静まりかえる。')}
    else if(guard.hp===3){say('番人の足が速くなった。');sfx('charge')}}}
/* One knock on one mark. The right next mark advances the seal; a wrong
   one resets it (the struck mark still counts as a first step when it IS
   the first - a player re-starting the phrase should not need a dead
   knock). Solving with the key already loose or held breaks the seal and
   nothing else: two keys would be a dungeon with a spare under the mat. */
function knock(mark,tx,ty){if(state!=='play')return;
  if(ksolved){say('印はもう静かだ。');sfx('step');return}
  if(KORDER[kprog]===mark){kprog++;sfx('step');
    burst(OX+tx*TILE+TILE/2,OY+ty*TILE+TILE/2,8,'ACCENT_JUICE');
    if(kprog>=3){ksolved=true;sfx('powerup');
      if(!hero.key&&!keyDrop){keyDrop={x:hero.x,y:hero.y};
        say('封が解けて、鍵が転がり出た。')}
      else{say('封が解けた。')}}
    else{say('印が低く鳴った（'+kprog+'/3）。')}}
  else{kprog=(KORDER[0]===mark)?1:0;
    say('印は沈黙した。順が違う。');sfx('clash')}}
/* One shove, and it obeys the walls (§1 の hitstop/knockback の対, C-1643).
   Every other mover on this page asks solid() before it assigns - the hero
   (below), the roamers, the guardian. The two knockbacks did not: they
   wrote straight into hero.x, so a hit taken beside a wall put the hero
   INSIDE it. The walls here are not decoration - solid() counts the
   shrine (9) and the optional door (10), which are §3's lock and key -
   so a blow could carry the hero through the structure the dungeon is
   built on. Axis by axis, as moveHero does it, so a shove along a wall
   still slides instead of stopping dead. */
function shove(dx,dy){const r=10;
  const nx=hero.x+dx;
  if(!solid(nx-r,hero.y-r)&&!solid(nx+r,hero.y-r)&&!solid(nx-r,hero.y+r)&&!solid(nx+r,hero.y+r)){hero.x=nx}
  const ny=hero.y+dy;
  if(!solid(hero.x-r,ny-r)&&!solid(hero.x+r,ny-r)&&!solid(hero.x-r,ny+r)&&!solid(hero.x+r,ny+r)){hero.y=ny}}
function moveHero(){
  let vx=0,vy=0;const sp=2.2;
  if(keys['arrowleft']||keys['a']){vx=-sp;hero.dir=3}
  if(keys['arrowright']||keys['d']){vx=sp;hero.dir=1}
  if(keys['arrowup']||keys['w']){vy=-sp;hero.dir=0}
  if(keys['arrowdown']||keys['s']){vy=sp;hero.dir=2}
  const nx=hero.x+vx,ny=hero.y+vy,r=10;
  if(!solid(nx-r,hero.y-r)&&!solid(nx+r,hero.y-r)&&!solid(nx-r,hero.y+r)&&!solid(nx+r,hero.y+r)){hero.x=nx}
  if(!solid(hero.x-r,ny-r)&&!solid(hero.x+r,ny-r)&&!solid(hero.x-r,ny+r)&&!solid(hero.x+r,ny+r)){hero.y=ny}
  const t=tileAt(hero.x,hero.y);
  if(t===5&&room<2){room++;hero.x=OX+TILE+6;say(NAMES[room]);sfx('step');
    hero.inv=Math.max(hero.inv,45)}
  else if(t===6&&room>0){room--;hero.x=OX+(GW-2)*TILE+26;say(NAMES[room]);sfx('step');
    hero.inv=Math.max(hero.inv,45)}
  if(t===11){rooms[room][Math.floor((hero.y-OY)/TILE)][Math.floor((hero.x-OX)/TILE)]=0;
    hero.charm=true;hero.hp=hero.maxhp;
    /* The charm is a one-time life - a power's voice, not a lock's. */
    say('護符を見つけた。一度だけ身代わりになる。');sfx('powerup');
    burst(hero.x,hero.y,20,'ALERT_JUICE')}
  if(keyDrop&&room===1&&Math.hypot(hero.x-keyDrop.x,hero.y-keyDrop.y)<20){
    hero.key=true;keyDrop=null;say('鍵を手に入れた。');sfx('key')}}
/* The talisman finally guards (§3, C-1323): one fatal hit is taken by
   the charm instead - it shatters, the hero stands at 1, and the mercy
   frames outlast a normal hit's. Once only: a shield that reforms would
   be immortality wearing an amulet. */
function charmSave(){if(!hero.charm)return false;
  hero.charm=false;hero.hp=1;hero.inv=90;
  sfx('clash');shake(8);burst(hero.x,hero.y,18,'ACCENT_JUICE');
  say('護符が砕けて、身代わりになった。');return true}
function moveEnemies(){enemies[room].forEach(en=>{if(!en.alive)return;en.t--;
  const d=Math.hypot(hero.x-en.x,hero.y-en.y);
  /* Exactly on top of the hero is d===0, and dividing by it makes this
     enemy's velocity NaN for the rest of the page: `solid(NaN,..)` then
     reads rooms[room][NaN] and throws, which stops the loop and ends the
     game with no message. Reachable in play - the knock-back below pushes
     the hero *along* the enemy's heading - so the guard is a fix, not a
     probe convenience. At zero distance there is no direction to chase
     anyway; the contact damage a few lines down is what should happen. */
  if(d<TILE*4){const towards=d||1;
    en.dx=(hero.x-en.x)/towards*ESPEED;en.dy=(hero.y-en.y)/towards*ESPEED}
  else if(en.t<=0){const a=rand()*6.28318;
    en.dx=Math.cos(a)*ESPEED*0.6;en.dy=Math.sin(a)*ESPEED*0.6;en.t=50+rand()*60}
  const nx=en.x+en.dx,ny=en.y+en.dy;
  if(!solid(nx,en.y)){en.x=nx}if(!solid(en.x,ny)){en.y=ny}
  if(hero.inv<=0&&d<16){hero.hp--;hurtRoam++;hero.inv=60;
    sfx('hurt',1,hero.x/cv.width);
    shake(9);hitstop(4);burst(hero.x,hero.y,12,'ALERT_JUICE');
    if(!REDUCED){hero.sq=0.7}
    /* Away from whoever landed it (C-1643). The roamer CHASES, so its own
       dx points at the hero; shoving by -en.dx dragged the hero toward its
       attacker - the opposite of what a knockback is for, and the opposite
       of the form the guardian below already used. */
    const kd=Math.hypot(hero.x-en.x,hero.y-en.y);
    if(kd>0.001){shove((hero.x-en.x)/kd*12,(hero.y-en.y)/kd*12)}
    else{const ed=Math.hypot(en.dx,en.dy)||1;shove(en.dx/ed*12,en.dy/ed*12)}
    if(hero.hp<=0){if(!charmSave()){state='over';failBeat(hero.x,hero.y)}}
    else{say('いたい。')}}})}
/* The guardian's turn (§6): a slow stride whose weight is the step, a held
   wind-up - the flash beat - then a charge that ends in dust. Phase 2 is
   the same grammar faster. speed/wind are read off guardFacts by the probe
   so the escalation is a measured fact, not a table. */
function guardSpeed(){return (guard.hp<=3?0.85:0.5)*Math.max(0.6,ESPEED)}
function guardWind(){return guard.hp<=3?20:34}
function moveGuard(){if(room!==2||!guard||!guard.alive)return;
  if(guard.inv>0)guard.inv--;
  if(guard.hurt>0)guard.hurt--;
  if(guard.smoke>0)guard.smoke--;
  const d=Math.hypot(hero.x-guard.x,hero.y-guard.y)||1;
  if(guard.mode==='stride'){
    const sp=guardSpeed();
    guard.dx=(hero.x-guard.x)/d*sp;guard.dy=(hero.y-guard.y)/d*sp;
    const nx=guard.x+guard.dx,ny=guard.y+guard.dy;
    if(!solid(nx,guard.y))guard.x=nx;if(!solid(guard.x,ny))guard.y=ny;
    /* Heavy feet: dust on the beat, slower than any small enemy moves. */
    if(++guard.step%36===0){burst(guard.x,guard.y+16,5,'ACCENT_JUICE');sfx('step')}
    if(d<TILE*5&&--guard.t<=0){guard.mode='wind';guard.wind=guardWind();
      sfx('charge')}}
  else if(guard.mode==='wind'){
    if(--guard.wind<=0){guard.mode='charge';guard.chg=24;
      guard.dx=(hero.x-guard.x)/d*3.2;guard.dy=(hero.y-guard.y)/d*3.2}}
  else if(guard.mode==='charge'){
    const nx=guard.x+guard.dx,ny=guard.y+guard.dy;
    let hitWall=false;
    if(!solid(nx,guard.y))guard.x=nx;else hitWall=true;
    if(!solid(guard.x,ny))guard.y=ny;else hitWall=true;
    if(hitWall||--guard.chg<=0){guard.mode='stride';guard.t=70;
      shake(7);burst(guard.x,guard.y+14,12,'ACCENT_JUICE')}}
  if(hero.inv<=0&&Math.hypot(hero.x-guard.x,hero.y-guard.y)<24){
    hero.hp--;hurtGuard++;hero.inv=60;sfx('hurt',1,hero.x/cv.width);
    shake(10);hitstop(5);
    burst(hero.x,hero.y,14,'ALERT_JUICE');
    if(!REDUCED){hero.sq=0.7}
    /* The same shove, through the same walls test (C-1643). The distance
       is taken fresh: `d` was measured before the guardian took its step,
       so the old line pushed along a direction the guardian had already
       left, and the shove came out diagonal to the blow. */
    const gd=Math.hypot(hero.x-guard.x,hero.y-guard.y)||1;
    shove((hero.x-guard.x)/gd*20,(hero.y-guard.y)/gd*20);
    if(hero.hp<=0){if(!charmSave()){state='over';failBeat(hero.x,hero.y)}}
    else{say('重い一撃。')}}}
function hurtFacts(){return {roam:hurtRoam,guard:hurtGuard,
  total:hurtRoam+hurtGuard,hp:hero.hp,state:state,sq:hero.sq}}
function guardFacts(){return guard?{alive:guard.alive,hp:guard.hp,max:guard.max,
  mode:guard.mode,wind:guard.wind,x:guard.x,y:guard.y,inv:guard.inv,
  speed:guardSpeed(),windFrames:guardWind(),
  hurt:guard.hurt,smoke:guard.smoke,
  phase:guard.hp<=3?2:1}:null}
/* Permanence, as facts (§23, C-1374): where the fallen lie. draw() and
   this read the same WRECK_A, so declared and painted cannot drift. The
   marks come from the same per-room array the fight used - nothing is
   copied, so walking away and coming back finds them by construction. */
const WRECK_A=0.5;
function wreckFacts(){return {alpha:WRECK_A,
  marks:(enemies[room]||[]).filter(e=>!e.alive).map(e=>({x:e.x,y:e.y})),
  guard:room===2&&guard?!guard.alive:null}}
const GROUND={0:'SURFACE_TOKEN',5:'SURFACE_TOKEN',6:'SURFACE_TOKEN'};
/* Readability rules from the knowledge base (game-design-notes.md §4):
   walls differ from floor by VALUE and FORM (edge highlights), never by hue
   alone; doors carry a shaped marker; water reads by motion and shade. */
function drawTile(t,x,y,now){
  cx.fillStyle=scenePaint(GROUND[t]||'SURFACE_TOKEN');cx.fillRect(x,y,TILE,TILE);
  if(t===0||t===5||t===6){cx.fillStyle='#ffffff10';cx.fillRect(x+1,y+1,2,2)}
  if(t===1){cx.fillStyle=scenePaint('BORDER_TOKEN');cx.fillRect(x,y,TILE,TILE);
    cx.fillStyle='#ffffff2e';cx.fillRect(x,y,TILE,3);
    cx.fillStyle='#00000055';cx.fillRect(x,y+TILE-4,TILE,4);
    sprite('rock',x+2,y+2,TILE-4,TILE-4,'')}
  if(t===2){cx.fillStyle='#20402f';cx.fillRect(x+3,y+3,TILE-6,TILE-6);
    sprite('bush',x+4,y+4,TILE-8,TILE-8,'#2c5a3f');
    cx.fillStyle='CYAN_TOKEN';cx.fillRect(x+13,y+13,4,4)}
  if(t===3){cx.fillStyle='#123f5a';cx.fillRect(x,y,TILE,TILE);
    const wv=FRAME(4,10,now)*2;
    cx.fillStyle='#2a6a8f';cx.fillRect(x+4,y+8+wv,TILE-8,2);
    cx.fillRect(x+8,y+20-wv,TILE-16,2)}
  if(t===5||t===6){const d=t===5?1:-1;
    cx.fillStyle='CYAN_TOKEN';cx.beginPath();
    cx.moveTo(x+16-6*d,y+8);cx.lineTo(x+16+8*d,y+16);cx.lineTo(x+16-6*d,y+24);
    cx.closePath();cx.fill();
    cx.fillStyle='#ffffff22';cx.fillRect(x+(d>0?TILE-3:0),y,3,TILE)}
  if(t===4){cx.fillStyle='RAISED_TOKEN';cx.fillRect(x+2,y+2,TILE-4,TILE-4);
    const fl=[3,5,4,6][FRAME(4,7,now)];
    cx.fillStyle='#e8a33d';cx.fillRect(x+12,y+8,8,8+fl)}
  if(t===7){cx.fillStyle='#7a5a2e';cx.fillRect(x+4,y+8,TILE-8,TILE-12);
    cx.fillStyle='CYAN_TOKEN';cx.fillRect(x+13,y+14,6,6)}
  if(t===8){sprite('npc',x+6,y+4,TILE-12,TILE-8,'#c8b28a');
    cx.fillStyle='MAGENTA_TOKEN';cx.fillRect(x+8,y+2,TILE-16,6)}
  /* Shapes, not tints (C-1018's lesson): the shrine is a gate, the optional
     door wears the diamond it costs, the charm is that diamond loose. */
  if(t===9){cx.fillStyle='RAISED_TOKEN';cx.fillRect(x+4,y+6,TILE-8,TILE-10);
    cx.fillStyle='BORDER_TOKEN';cx.fillRect(x+2,y+4,TILE-4,4);
    cx.fillRect(x+7,y+10,4,TILE-14);cx.fillRect(x+TILE-11,y+10,4,TILE-14)}
  if(t===10){cx.fillStyle='#5a4a2e';cx.fillRect(x+3,y+4,TILE-6,TILE-8);
    cx.strokeStyle='ALERT_JUICE';cx.lineWidth=2;diamond(x+TILE/2,y+TILE/2,6);
    cx.stroke();cx.lineWidth=1}
  if(t===11){cx.fillStyle='ALERT_JUICE';diamond(x+TILE/2,y+TILE/2,8);cx.fill()}
  /* The stone and the marks carry their names as glyphs (§4: form and
     text, never colour alone). */
  if(t===12){cx.fillStyle='RAISED_TOKEN';cx.fillRect(x+5,y+3,TILE-10,TILE-6);
    cx.fillStyle='#00000055';cx.fillRect(x+5,y+TILE-7,TILE-10,4);
    cx.fillStyle='INK_TOKEN';cx.font='13px ui-monospace,monospace';
    cx.fillText('碑',x+9,y+19)}
  if(t===13||t===14||t===15){cx.fillStyle='RAISED_TOKEN';
    cx.fillRect(x+4,y+6,TILE-8,TILE-10);
    cx.fillStyle='#ffffff2e';cx.fillRect(x+4,y+6,TILE-8,3);
    cx.fillStyle='INK_TOKEN';cx.font='13px ui-monospace,monospace';
    cx.fillText(KMARKS[t-13],x+9,y+21)}}
function diamond(cxp,cyp,r){cx.beginPath();cx.moveTo(cxp,cyp-r);
  cx.lineTo(cxp+r,cyp);cx.lineTo(cxp,cyp+r);cx.lineTo(cxp-r,cyp);cx.closePath()}
function draw(now){
  /* 森 -> 洞窟 -> 祭壇: the room, not the theme, picks the accent hue, and
     the altar keeps the brightest值 in the game for last (§7 観察 5-6). */
  setScene(room);
  cx.fillStyle=scenePaint('BG_TOKEN');cx.fillRect(0,0,cv.width,cv.height);
  for(let y=0;y<GH;y++){for(let x=0;x<GW;x++){
    drawTile(rooms[room][y][x],OX+x*TILE,OY+y*TILE,now)}}
  if(keyDrop&&room===1){cx.fillStyle='CYAN_TOKEN';
    cx.fillRect(keyDrop.x-4,keyDrop.y-7,8,10);cx.fillRect(keyDrop.x-1,keyDrop.y-1,6,3)}
  /* Permanence (§23, C-1374): a beaten enemy is not erased - a flat husk
     stays where it fell for as long as the world does (walk away, come
     back: still there). Static paint under the live sprites, so REDUCED
     keeps it too - a consequence, not a motion. */
  cx.globalAlpha=WRECK_A;cx.fillStyle='MAGENTA_TOKEN';
  (enemies[room]||[]).forEach(en=>{if(en.alive)return;
    cx.fillRect(en.x-10,en.y+2,20,7)});
  if(room===2&&guard&&!guard.alive){
    cx.fillRect(guard.x-20,guard.y+6,40,11)}
  cx.globalAlpha=1;
  enemies[room].forEach(en=>{if(!en.alive)return;
    const bob=[0,-2,0,2][FRAME(4,9,now)];
    sprite('enemy',en.x-10,en.y-10+bob,20,20,'MAGENTA_TOKEN')});
  if(room===2&&guard&&guard.alive){
    /* Twice the hero's size, on a slower beat than any small enemy - the
       weight is the stride (§6 観察 2). The wind-up is the held flash
       beat; under reduced motion the same warning is a steady outline. */
    const gb=[0,-1,0,1][FRAME(4,13,now)];
    const winding=guard.mode==='wind';
    /* The blow's first beat (§6 観察 2, C-1343): one flash, same as the
       kaiju leg's, before the smoke takes over. */
    cx.fillStyle=guard.hurt>0?'#dfe7f5':
      (winding&&!REDUCED&&FRAME(2,4,now)===0)?'#dfe7f5':'MAGENTA_TOKEN';
    cx.fillRect(guard.x-20,guard.y-18+gb,40,36);
    cx.beginPath();cx.moveTo(guard.x-20,guard.y-18+gb);
    cx.lineTo(guard.x-12,guard.y-30+gb);cx.lineTo(guard.x-6,guard.y-18+gb);
    cx.moveTo(guard.x+20,guard.y-18+gb);
    cx.lineTo(guard.x+12,guard.y-30+gb);cx.lineTo(guard.x+6,guard.y-18+gb);
    cx.closePath();cx.fill();
    cx.fillStyle='#05070f';
    cx.fillRect(guard.x-13,guard.y-8+gb,8,7);cx.fillRect(guard.x+5,guard.y-8+gb,8,7);
    if(winding&&REDUCED){cx.strokeStyle='#dfe7f5';cx.lineWidth=3;
      cx.strokeRect(guard.x-23,guard.y-21,46,42);cx.lineWidth=1}
    /* Beats two and three: smoke that stays after the flash is gone, and
       the silhouette re-emerging as it thins (観察 2). */
    if(guard.smoke>0){cx.fillStyle='#dfe7f5';cx.globalAlpha=guard.smoke/70;
      cx.beginPath();cx.arc(guard.x,guard.y-6+gb,30,0,6.283);cx.fill();
      cx.globalAlpha=1}
    for(let i=0;i<guard.max;i++){cx.strokeStyle='#dfe7f5';
      cx.strokeRect(guard.x-19.5+i*6.5,guard.y-37.5,5,5)}
    cx.fillStyle='#dfe7f5';
    for(let i=0;i<guard.hp;i++){cx.fillRect(guard.x-19+i*6.5,guard.y-37,4,4)}}
  if(!(hero.inv>0&&FRAME(2,3,now)===1)){
    /* The hit crush (§1, C-1387): one bottom-anchored joint transform -
       body, hat bar and both eyes squash together (parts sliding apart
       read as a glitch, C-1385's judgement). Bit-identical at sq=1. */
    const hsq=hero.sq,hsw=2-hsq,hb=hero.y+10;
    sprite('hero',hero.x-10*hsw,hb-18*hsq,20*hsw,18*hsq,'CYAN_TOKEN');
    cx.fillStyle='#0a2a33';cx.fillRect(hero.x-11*hsw,hb-24*hsq,22*hsw,7*hsq);
    /* Eyes under the hat brim (§1, C-1351): the guard above already has
       them and the hero did not. Three states for a four-way walker -
       right leans them right, left leans left, front is centred - and
       facing up is the back of the head, so no eyes at all. The blink is
       one FRAME beat, pinned open under reduced motion. */
    const fc=faceFacts();
    if(fc.shown&&!fc.blink){cx.fillStyle='#05070f';
      const ex=[0,2.5,0,-2.5][hero.dir];
      cx.fillRect(hero.x+(ex-5.5)*hsw,hb-16*hsq,2.5*hsw,3*hsq);
      cx.fillRect(hero.x+(ex+3)*hsw,hb-16*hsq,2.5*hsw,3*hsq)}}
  /* The blink is motion, so reduced motion pins the hero solid - which
     used to erase the invulnerability entirely: no flash, no ring,
     nothing but the heart row and a sound. The guardian's wind-up
     already answers this with a steady outline (C-1343's rule made
     visual), so the hero's mercy window gets the same one: drawn only
     under REDUCED, only while inv runs, gone the frame it expires
     (§4×§15, C-1386). */
  if(hero.inv>0&&REDUCED){cx.strokeStyle='#dfe7f5';cx.lineWidth=2;
    cx.strokeRect(hero.x-13,hero.y-17,26,28);cx.lineWidth=1}
  if(hero.swing>0){const p=ease(hero.swing/10);cx.strokeStyle='#dfe7f5';
    cx.lineWidth=3;cx.beginPath();
    const ang=[[-2.2,-0.9],[-0.7,0.7],[0.9,2.2],[2.4,3.9]][hero.dir];
    cx.arc(hero.x,hero.y,22,ang[0]+p,ang[1]+p);cx.stroke();cx.lineWidth=1}
  if(room===1){cx.fillStyle='#02030a';cx.globalAlpha=REDUCED?0.35:0.35+0.04*FRAME(2,11,now);
    cx.fillRect(0,0,cv.width,cv.height);cx.globalAlpha=1;
    [[6,0],[13,0]].forEach(p=>{glow(OX+p[0]*TILE+16,OY+16,86,now)});
    glow(hero.x,hero.y,64,now)}
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(OX-4,0,GW*TILE+8,16);cx.globalAlpha=1;
  cx.fillStyle='MAGENTA_TOKEN';
  for(let i=0;i<hero.maxhp;i++){cx.strokeStyle='MAGENTA_TOKEN';
    cx.strokeRect(OX+i*18+0.5,2.5,13,9)}
  for(let i=0;i<hero.hp;i++){cx.fillRect(OX+i*18,2,14,10)}
  cx.fillStyle=HUD_INK;cx.font='13px ui-monospace,monospace';
  cx.fillText('宝石 '+hero.gems+(hero.key?'  鍵あり':'')+(hero.charm?'  護符':''),
    OX+70,11);
  cx.fillText(NAMES[room],cv.width-OX-150,11);
  if(msgT>0){msgT--;cx.fillStyle='SCRIM_TOKEN'+'d9';
    cx.fillRect(OX,cv.height-34,GW*TILE,26);cx.fillStyle='INK_TOKEN';
    cx.fillText(msg,OX+10,cv.height-16)}
  if(state==='win'){shade('宝箱をあけた。冒険の勝利。',
    '宝石 '+hero.gems+' 個 / 護符 '+(hero.charm?'あり':'なし')+(((typeof roundAskReady!=='function'||roundAskReady()))?' / R か タップでもう一度':''))}
  if(state==='over'){shade('ちからつきた。','R か タップでやり直す')}}
function glow(x,y,r,now){const g=cx.createRadialGradient(x,y,4,x,y,r);
  g.addColorStop(0,'#f5d89a55');g.addColorStop(1,'#00000000');
  cx.fillStyle=g;cx.fillRect(x-r,y-r,r*2,r*2)}
function shade(a,b){cx.fillStyle='SCRIM_TOKEN'+'d0';cx.fillRect(0,0,cv.width,cv.height);
  cx.fillStyle='INK_TOKEN';cx.font='20px ui-monospace,monospace';
  cx.fillText(a,cv.width/2-a.length*10,cv.height/2-8);
  cx.font='13px ui-monospace,monospace';
  cx.fillText(b,cv.width/2-b.length*6.5,cv.height/2+18)}
function step(rt){const now=performance.now();
  /* The world advances on real time, not on this display's refresh
     rate (§26, C-1608 — the gate C-1607 built and racing proved).
     Drawing is NOT gated: a 120Hz screen still gets 120 pictures a
     second, the world just stops happening twice as fast. */
  if(!TICK(rt)){draw(now);return requestAnimationFrame(step)}
  worldStep();
  /* Only fighting when something is actually near: the quiet stretches of a
     dungeon are what make the loud ones read as loud (§6 観察 4). */
  combat(state==='play'&&gateState()==='playing'&&
    ((enemies[room]||[]).some(e=>e.alive&&Math.hypot(e.x-hero.x,e.y-hero.y)<120)
     ||(room===2&&guard!==null&&guard.alive&&Math.hypot(guard.x-hero.x,guard.y-hero.y)<160)));
  /* The hit crush recovers even on the over screen (racing's reason,
     C-1385): the settle lives outside the play guard (§1, C-1387). */
  hero.sq+=(1-hero.sq)*0.25;if(Math.abs(hero.sq-1)<0.01)hero.sq=1;
  if(state==='play'){
    if(hero.swing>0){hero.swing--;
      if(hero.swing===0&&hero.queued){hero.queued=false;swing()}}
    if(hero.inv>0)hero.inv--;
    moveHero();moveEnemies();moveGuard()}
  draw(now);requestAnimationFrame(step)}
reset();step();
"""

#: Enough of a browser to let the real page's script run to its first frame
#: in node. Every drawing call becomes a no-op through one proxy, so the
#: world it builds can be read back instead of inferred from source text -
#: "the tile is defined" and "the tile is on the map" were different facts
#: once already (C-1018, the pond that shipped as dead code).
WORLD_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
globalThis.performance = { now: () => 0 };
globalThis.requestAnimationFrame = () => 0;
globalThis.addEventListener = () => {};
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
SCRIPT_PLACEHOLDER
const tally = {};
rooms.forEach(m => m.forEach(r => r.forEach(t => { tally[t] = (tally[t]||0) + 1 })));
/* What sits around the reward decides whether the door is a door or a
   decoration: a second way in makes the "optional branch" a straight line
   with an ornament on it. */
let around = [];
rooms.forEach(m => m.forEach((r, y) => r.forEach((t, x) => { if (t === 11) {
  around = [[0,-1],[0,1],[-1,0],[1,0]].map(d => (m[y+d[1]]||[])[x+d[0]]) } })));
const palette = sceneFacts();
const hud = hudFacts();
console.log(JSON.stringify({
  tiles: tally,
  scenes: palette.scenes,
  hud: hud,
  charmNeighbours: around,
  hearts: hero.maxhp,
  charm: hero.charm,
  gems: hero.gems,
}));
"""


#: The queued blow, played (C-1311): a press during the swing fires the
#: frame the arm is free; a single press swings exactly once.
COMBO_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(2);
/* Double press: the second lands mid-swing and must fire at its end. */
hero.swing = 0; hero.queued = false;
key(' ');
const firstSwing = hero.swing;
run(3);
key(' ');
const midSwing = hero.swing, keptQueue = hero.queued === true;
run(8);
const secondSwing = hero.swing;
/* Single press: exactly one swing, then quiet. */
run(20); hero.queued = false;
key(' ');
run(14);
const afterSingle = hero.swing, ghostQueue = hero.queued === true;
console.log(JSON.stringify({ firstSwing: firstSwing, midSwing: midSwing,
  keptQueue: keptQueue, secondSwing: secondSwing,
  afterSingle: afterSingle, ghostQueue: ghostQueue }));
"""


def combo_probe(script: str) -> str:
    """The page's own script, wrapped so a queued swing can be watched."""

    return COMBO_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The guardian fought in node: the same no-op browser, the fight driven by
#: hand. The probe teleports and heals the hero (the racing probe's
#: ``obs.push`` licence - state moved so a rule can be read), but every
#: rule it reports comes off the running page: the chest that refuses a
#: key while the guardian stands, the armour that turns mashing into one
#: blow, the phase-2 re-acceleration, the win that only follows the fall.
#: The talisman, hit for real (§3, C-1323): a fatal blow lands on a
#: charm-bearing hero at 1 hp - once it is a save, twice it is a death.
CHARM_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(2);
/* A charm-bearer at one heart takes a fatal blow: the charm shatters in
   the hero's place. The enemy is placed on the hero, the same way the
   audio probe meets the combat clause. */
hero.charm = true; hero.hp = 1; hero.inv = 0;
(enemies[room] = enemies[room] || []).push(
  { x: hero.x, y: hero.y, dx: 0, dy: 0, t: 999, alive: true });
run(3);
const afterSave = { hp: hero.hp, charm: hero.charm, inv: hero.inv,
  state: state, beats: failBeats() };
/* The same blow again, charm spent: an ordinary death, with its beat. */
hero.inv = 0; hero.hp = 1;
run(3);
const afterDeath = { hp: hero.hp, charm: hero.charm, state: state,
  beats: failBeats() };
console.log(JSON.stringify({ afterSave: afterSave, afterDeath: afterDeath }));
"""


def charm_probe(script: str) -> str:
    """The page's own script, wrapped so the talisman can be struck."""

    return CHARM_PROBE.replace("SCRIPT_PLACEHOLDER", script)


GUARD_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(2);
/* Into the altar with the key, as if the dungeon were done. */
room = 2; hero.key = true; hero.x = OX + 6 * TILE; hero.y = OY + 4 * TILE + 16;
const first = guardFacts();
/* The chest, while the guardian stands. */
hero.x = OX + 9 * TILE + 16; hero.y = OY + 4 * TILE + 16; hero.dir = 1; hero.swing = 0;
key(' '); run(1);
const lockedState = state;
/* Two blows one frame apart: the armour should count one. */
hero.hp = 99; hero.swing = 0;
hero.x = guard.x - 26; hero.y = guard.y; hero.dir = 1;
key(' '); const hpA = guard.hp;
run(1); hero.swing = 0;
hero.x = guard.x - 26; hero.y = guard.y;
key(' '); const hpB = guard.hp;
const p1 = { speed: guardFacts().speed, wind: guardFacts().windFrames };
/* Fight it down, noting the turn it takes and what phase 2 measures. */
let sawWind = false, sawCharge = false, p2 = null, turns = 0;
while (guardFacts() && guardFacts().alive && turns++ < 3000) {
  hero.hp = 99;
  const g = guardFacts();
  if (g.mode === 'wind') sawWind = true;
  if (g.mode === 'charge') sawCharge = true;
  if (g.phase === 2 && p2 === null) p2 = { speed: g.speed, wind: g.windFrames };
  if (g.inv <= 0 && hero.swing <= 0) {
    hero.x = g.x - 26; hero.y = g.y; hero.dir = 1; key(' ');
  }
  run(2);
}
const fallen = guardFacts();
/* The same chest, after the fall. */
hero.x = OX + 9 * TILE + 16; hero.y = OY + 4 * TILE + 16; hero.dir = 1; hero.swing = 0;
key(' '); run(1);
console.log(JSON.stringify({
  firstAlive: first.alive, firstHp: first.hp, firstMax: first.max,
  lockedState: lockedState, hpA: hpA, hpB: hpB,
  p1: p1, p2: p2, sawWind: sawWind, sawCharge: sawCharge,
  fallenAlive: fallen.alive, finalState: state, turns: turns,
  wreck: wreckFacts(),
}));
"""


def guard_probe(script: str) -> str:
    """The page's own script, wrapped so the guardian can be fought."""

    return GUARD_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The dungeon, walked (§3, C-1675).
#:
#: ``GUARD_PROBE`` reaches ``state='win'`` by writing ``hero.key = true``
#: and stepping into room 2, which proves the chest opens for its key and
#: nothing about how the key is got. ``creation_adventure_playable``
#: counts rooms and tiles in the generated page and runs no frames at
#: all. So the mission graph §3 calls the skeleton - clear the roamers,
#: the key falls, pick it up, cross to the altar, fell the guardian, open
#: the chest - had never been walked end to end.
#:
#: Walked here three ways, with no flag set by hand: once to the win
#: without touching the optional door, the charm or a single gem (the
#: promise the source has carried in a comment since C-1021); once with
#: the fallen key left on the floor, which must not win; and once
#: counting the roamers down, because a key that fell early would make
#: the lock a decoration.
RUN_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(2);
function findTile(r, want){
  for (let ty = 0; ty < GH; ty++) for (let tx = 0; tx < GW; tx++)
    if (rooms[r][ty][tx] === want) return [tx, ty];
  return null }
function faceTile(tx, ty){
  hero.x = OX + tx * TILE + TILE / 2 - 20; hero.y = OY + ty * TILE + TILE / 2;
  hero.dir = 1 }
/* A blow leaves three frames of hitstop, and the tile a player is
   standing on is read by the walk - so a single frame after a kill is
   the frozen one, and the pickup would never be seen. */
const SETTLE = 8;
function clearRoom1(){
  let swings = 0;
  const countdown = [];
  for (let i = 0; i < 60 && enemies[1].some(e => e.alive); i++) {
    const en = enemies[1].find(e => e.alive);
    hero.hp = 99; hero.swing = 0;
    hero.x = en.x - 20; hero.y = en.y; hero.dir = 1;
    key(' '); run(1); swings++;
    countdown.push({ left: enemies[1].filter(e => e.alive).length, drop: !!keyDrop });
  }
  return { swings: swings, countdown: countdown,
    cleared: enemies[1].every(e => !e.alive) };
}
function attempt(takeKey){
  reset();
  room = 1; hero.hp = 99;
  const room1 = clearRoom1();
  const dropped = !!keyDrop;
  if (takeKey && keyDrop) { hero.x = keyDrop.x; hero.y = keyDrop.y; run(SETTLE) }
  const held = hero.key;
  room = 2; hero.hp = 99;
  const chest = findTile(2, 7);
  /* The chest while the guardian stands, before anything else. */
  faceTile(chest[0], chest[1]); hero.swing = 0; key(' '); run(SETTLE);
  const guarded = state;
  let turns = 0;
  while (guardFacts() && guardFacts().alive && turns++ < 3000) {
    hero.hp = 99;
    const g = guardFacts();
    if (g.inv <= 0 && hero.swing <= 0) {
      hero.x = g.x - 26; hero.y = g.y; hero.dir = 1; key(' ') }
    run(2);
  }
  const fell = !guardFacts().alive;
  faceTile(chest[0], chest[1]); hero.swing = 0; key(' '); run(SETTLE);
  return { swings: room1.swings, cleared: room1.cleared,
    countdown: room1.countdown, dropped: dropped, held: held,
    guarded: guarded, fell: fell, turns: turns, state: state,
    gems: hero.gems, charm: hero.charm, hearts: hero.maxhp,
    doorStands: findTile(1, 10) !== null,
    rewardStands: findTile(1, 11) !== null };
}
const walked = attempt(true);
const leftBehind = attempt(false);
console.log(JSON.stringify({ walked: walked, leftBehind: leftBehind }));
"""


def run_probe(script: str) -> str:
    """The page's own script, wrapped so the dungeon can be walked."""

    return RUN_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: A kill, an exit, a return (§23, C-1374): the husk must lie where the
#: enemy fell, survive leaving the room, and the fallen guardian must
#: leave one too. Driven with the sword, not by flipping flags - except
#: the guardian, whose 3000-turn fight GUARD_PROBE already runs; here its
#: hp is set to 1 so one real blow fells it through the same code path.
WRECK_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(2);
/* Into the cave, blade to the first enemy. */
room = 1;
const en = enemies[1][0];
hero.hp = 99;
hero.x = en.x - 20; hero.y = en.y; hero.dir = 1; hero.swing = 0;
const before = wreckFacts().marks.length;
/* Where it stood when the blade fell - read BEFORE the kill, so a
   template that displaces its dead cannot move the anchor with them. */
const enemyAt = { x: en.x, y: en.y };
key(' '); run(1);
const afterKill = wreckFacts();
const aliveNow = enemies[1].filter(e => e.alive).length;
/* Walk away (the village), and come back: still there (§23). */
room = 0; run(30);
const awayMarks = wreckFacts().marks.length;
room = 1; run(30);
const back = wreckFacts();
/* The guardian falls by the same blade - one real blow on 1 hp. */
room = 2; hero.key = true;
guard.hp = 1; guard.inv = 0; hero.swing = 0;
hero.x = guard.x - 26; hero.y = guard.y; hero.dir = 1;
key(' '); run(1);
const guardWreck = wreckFacts().guard;
console.log(JSON.stringify({
  before: before, afterKill: afterKill, aliveNow: aliveNow,
  awayMarks: awayMarks, back: back, enemyAt: enemyAt,
  guardWreck: guardWreck,
}));
"""


def wreck_probe(script: str) -> str:
    """The page's own script, wrapped so the husks can be counted."""

    return WRECK_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The mercy window, seen without motion (§4×§15, C-1386): a REDUCED run
#: takes a real hit and the steady outline must stand while inv runs and
#: vanish the frame it expires; a normal run keeps its blink (frames
#: where the hero is not drawn) and never shows the outline.
HURT_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
let frameStrokes = [], frameFills = [];
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy({
    strokeRect: (x, y, w, h) => { frameStrokes.push([w, h]) },
    fillRect: (x, y, w, h) => { frameFills.push([w, h]) } }, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: () => true }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function frame(){ frameStrokes = []; frameFills = [];
  if (queued) { const fn = queued; queued = null; fn((F++) * 16) }
  return { outline: frameStrokes.some(s => s[0] === 26 && s[1] === 28),
    hero: frameFills.some(f => f[0] === 22 && f[1] === 7) } }
function key(k){
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); frame(); frame();
/* Into the cave, onto an enemy: a real hit. */
room = 1;
const en = enemies[1][0];
hero.inv = 0; hero.hp = 3; hero.swing = 0;
hero.x = en.x; hero.y = en.y;
frame();
const hpAfter = hero.hp, invAfter = hero.inv;
/* Hold still through the mercy window and watch every frame. */
hero.x = OX + 2 * TILE; hero.y = OY + 4 * TILE;
let outlineFrames = 0, blinkGaps = 0, watched = 0;
while (hero.inv > 0 && watched++ < 90) {
  const f = frame();
  if (f.outline) outlineFrames++;
  if (!f.hero) blinkGaps++;
}
/* And past it: the outline must not outlive the window. */
let outlineAfter = 0;
for (let i = 0; i < 20; i++) { if (frame().outline) outlineAfter++ }
console.log(JSON.stringify({ hpAfter: hpAfter, invAfter: invAfter,
  watched: watched, outlineFrames: outlineFrames, blinkGaps: blinkGaps,
  outlineAfter: outlineAfter }));
"""



#: The two knockbacks, driven for real and judged by the page's OWN
#: solid() (§1 の hitstop/knockback の対, C-1643). Two things are read,
#: because a shove can be wrong in two independent ways: it can end
#: inside a wall - every other mover on this page asks first, and these
#: two did not - and it can point the wrong way, which is what the
#: roamer's `-en.dx` did to a roamer that chases. Positions are staged
#: against real map tiles rather than numbers, so the answer is the
#: dungeon's, not the probe's.
KNOCK_PROBE = KEY_EVENT_JS + """
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
PROBE_EYES_PLACEHOLDER
function frame(){ eeTick();
  if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }
function kbKey(k){
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
/* The hero's own footprint, at the radius the page's own mover uses. */
const KBR = 10;
function inWall(x, y){
  return solid(x-KBR,y-KBR)||solid(x+KBR,y-KBR)||solid(x-KBR,y+KBR)||solid(x+KBR,y+KBR) }
/* A floor tile with a solid neighbour on the named side, so the shove has
   somewhere to push the hero THROUGH. */
/* A floor tile with a wall on its LEFT and open floor on its RIGHT. One
   spot serves both halves: put the attacker on the right and the shove
   goes into the wall, put it on the left and the shove goes into the
   open. Chosen off the real map, so the geometry is the dungeon's. */
function spotBeside(rm){
  for (let ty = 1; ty < GH - 1; ty++) {
    for (let tx = 2; tx < GW - 2; tx++) {
      if (rooms[rm][ty][tx] !== 0) continue;
      const left = rooms[rm][ty][tx - 1], right = rooms[rm][ty][tx + 1];
      if ((left === 1 || left === 2) && right === 0) return { tx: tx, ty: ty } } }
  return null }
function stand(spot){
  hero.x = OX + spot.tx * TILE + TILE / 2;
  hero.y = OY + spot.ty * TILE + TILE / 2;
  hero.inv = 0; hero.hp = 3; hero.swing = 0 }
/* A hit spends a hitstop; run it out or the next frame is a frozen one
   and measures nothing at all. */
function settle(){ for (let i = 0; i < 24; i++) { frame() } }
function reading(before, from){
  /* What the page's own camera actually got kicked by (C-1648). §1 quotes
     Vlambeer: the shake is meant to be PROPORTIONAL to the weight of the
     event, and nothing checked that the heavier of two hits shakes more.
     Read through shakeAmount(), the page's own accessor, not off a
     literal - the same reason C-1640 stopped reading the palette table. */
  return { hp: hero.hp, hit: hero.hp < before.hp, shake: shakeAmount(),
    moved: Math.round(Math.hypot(hero.x - before.x, hero.y - before.y) * 100) / 100,
    inWall: inWall(hero.x, hero.y),
    /* Positive when the blow left the hero further from whoever threw it. */
    away: Math.round((Math.hypot(hero.x - from.x, hero.y - from.y)
        - Math.hypot(before.x - from.x, before.y - from.y)) * 100) / 100 } }
kbKey(' '); frame(); frame();

/* --- the roamer, shoved INTO the wall --- */
room = 1;
enemies[1].forEach(e => { e.alive = false });
const s1 = spotBeside(1);
const en = enemies[1][0];
stand(s1);
en.alive = true; en.x = hero.x + 4; en.y = hero.y; en.t = 999;
let before = { x: hero.x, y: hero.y, hp: hero.hp };
let from = { x: en.x, y: en.y };
frame();
const roamWall = reading(before, from);
settle();

/* --- the roamer, shoved into the OPEN --- */
enemies[1].forEach(e => { e.alive = false });
stand(s1);
en.alive = true; en.x = hero.x - 4; en.y = hero.y; en.t = 999;
before = { x: hero.x, y: hero.y, hp: hero.hp };
from = { x: en.x, y: en.y };
frame();
const roamOpen = reading(before, from);
settle();

/* --- the guardian, shoved INTO the wall --- */
room = 2;
const s2 = spotBeside(2);
stand(s2);
guard.alive = true; guard.mode = 'stride'; guard.t = 999; guard.inv = 0;
guard.x = hero.x + 6; guard.y = hero.y;
before = { x: hero.x, y: hero.y, hp: hero.hp };
frame();
from = { x: guard.x, y: guard.y };
const guardWall = reading(before, from);
settle();

/* --- the guardian, shoved into the OPEN --- */
stand(s2);
guard.alive = true; guard.mode = 'stride'; guard.t = 999; guard.inv = 0;
guard.x = hero.x - 6; guard.y = hero.y;
before = { x: hero.x, y: hero.y, hp: hero.hp };
frame();
from = { x: guard.x, y: guard.y };
const guardOpen = reading(before, from);

/* The ear and the eye on the same blow (§28, C-1653). Staged with the
   guardian as far from the hero as contact still allows (the page's own
   reach is 24px): at the 6px used above, naming the attacker instead of
   the victim moves the pan by 0.008, which no ear could hear and no
   contract should pretend to catch. Twenty pixels apart, the question
   is real. */
settle();
room = 2;
stand(s2);
guard.alive = true; guard.mode = 'stride'; guard.t = 999; guard.inv = 0;
guard.x = hero.x - 20; guard.y = hero.y;
for (let i = 0; i < 6 && hero.hp === 3; i++) {
  hero.inv = 0; hero.hp = 3;
  guard.x = hero.x - 20; guard.y = hero.y;
  frame();
}
const pair = earEye('hurt', cv.width);
console.log(JSON.stringify({ pair: pair, roamWall: roamWall, roamOpen: roamOpen,
  guardWall: guardWall, guardOpen: guardOpen }));
"""


def knock_probe(script: str) -> str:
    """The page's own script, wrapped so a shove can be watched land."""

    from sidra_ai.creation.probekit import PROBE_EARS, PROBE_EYES

    return (
        KNOCK_PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("PROBE_EARS_PLACEHOLDER", PROBE_EARS)
        .replace("PROBE_EYES_PLACEHOLDER", PROBE_EYES)
    )



#: Which act the dungeon was actually IN, in the order it went (C-1645).
#: The world probe reads the map without ever running a frame, so it can
#: say the three colours exist but not that the page went through them -
#: exactly the half C-1640's destruction showed a palette table cannot
#: cover. Here the hero really walks, through the page's own transition
#: tile, and SCENE is sampled after every frame.
SCENE_ORDER_PROBE = """
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
const sceneOrder = [];
function sceneTick(){
  if (typeof SCENE === 'number' && sceneOrder[sceneOrder.length - 1] !== SCENE) {
    sceneOrder.push(SCENE) } }
function frame(){ if (queued) { const fn = queued; queued = null; fn((F++) * 16); sceneTick() } }
PROBE_KEYS_PLACEHOLDER
function press(k, down){
  const e = probeKey(k);
  (handlers[down ? 'keydown' : 'keyup'] || []).forEach(fn => fn(e)) }
press(' ', true); press(' ', false); frame(); frame();
/* The door onward is tile 5. Stand just left of it and walk right, so the
   page's own moveHero() carries the room across - not an assignment from
   out here. Twice, because the dungeon is three rooms. */
function doorX(rm){
  for (let ty = 0; ty < GH; ty++) {
    for (let tx = 0; tx < GW; tx++) {
      if (rooms[rm][ty][tx] === 5) return { tx: tx, ty: ty } } }
  return null }
for (let leg = 0; leg < 2; leg++) {
  const door = doorX(room);
  if (door === null) break;
  hero.x = OX + (door.tx - 1) * TILE + TILE / 2;
  hero.y = OY + door.ty * TILE + TILE / 2;
  hero.inv = 90;
  const was = room;
  press('ArrowRight', true);
  for (let i = 0; i < 400 && room === was; i++) { frame() }
  press('ArrowRight', false);
  for (let i = 0; i < 4; i++) { frame() }
}
console.log(JSON.stringify({ sceneOrder: sceneOrder, room: room,
  scenes: sceneFacts().scenes.length }));
"""


def scene_order_probe(script: str) -> str:
    """The page's own script, wrapped so the walk between rooms is seen."""

    return with_probe_keys(SCENE_ORDER_PROBE.replace("SCRIPT_PLACEHOLDER", script))


def hurt_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the mercy window can be seen."""

    return HURT_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
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


#: The hit crush, driven (§1, C-1387): one real contact hit must sink the
#: hero to 0.7 through the squash channel, the silhouette must actually be
#: drawn crushed (the hat bar's recorded width and height follow the joint
#: transform), the crush must settle back to exactly 1 within half a
#: second, and under reduced motion the same hit lands with the outline
#: unchanged on every frame.
SQUASH_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: REDUCED_INPUT });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
let frameFills = [];
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => new Proxy({
    fillRect: (x, y, w, h) => { frameFills.push([w, h]) } }, {
    get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: () => true }) }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function frame(){ frameFills = [];
  if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }
function hatMatches(sq){ return frameFills.some(f =>
  Math.abs(f[0] - 22 * (2 - sq)) < 1e-6 && Math.abs(f[1] - 7 * sq) < 1e-6) }
function key(k){
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); frame(); frame();
/* Standing still, whole: the silhouette must not breathe on its own. */
let idleOff = 0;
for (let i = 0; i < 30; i++) { frame();
  if (hero.sq !== 1 || !hatMatches(1)) idleOff++ }
/* Into the cave, onto an enemy: a real hit. */
room = 1;
const en = enemies[1][0];
hero.inv = 0; hero.hp = 3; hero.swing = 0;
hero.x = en.x; hero.y = en.y;
frame();
const hp = hero.hp, hitSq = hero.sq;
/* Hold still and watch the crush drawn, then released. */
hero.x = OX + 2 * TILE; hero.y = OY + 4 * TILE;
let settled = null, crushedDrawn = 0;
for (let i = 0; i < 40; i++) { frame();
  /* < 0.95, not < 0.9: the deepest frames sit inside hitstop (no draw)
     and the blink can skip one more - the crushed band is what matters. */
  if (hero.sq < 0.95 && hatMatches(hero.sq)) crushedDrawn++;
  if (settled === null && hero.sq === 1) settled = i + 1 }
console.log(JSON.stringify({ idleOff: idleOff, hp: hp, hitSq: hitSq,
  crushedDrawn: crushedDrawn, settled: settled, restSq: hero.sq }));
"""


def squash_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the hit's crush can be watched."""

    return SQUASH_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    )


#: The dry run, driven (§5, C-1376): with the dice loaded to always miss,
#: the real blade cuts every tuft in the village and the floor must still
#: hand over 5 gems - the shrine's 3 with the door's 2 to spare - and the
#: shrine must actually accept them. A second pass with the dice loaded
#: to always hit checks the ceiling: 14 tufts, 14 gems, no pity fired.
ECON_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(2);
/* The dice, loaded. The world is already built, so only the cut rolls
   (and other runtime rolls) are touched. */
rand = () => DICE_PLACEHOLDER;
function cutAll(){
  let cuts = 0;
  for (let ty = 0; ty < GH; ty++) for (let tx = 0; tx < GW; tx++) {
    if (rooms[0][ty][tx] !== 2) continue;
    hero.hp = 99; hero.swing = 0;
    hero.x = OX + tx * TILE + TILE / 2 - 20;
    hero.y = OY + ty * TILE + TILE / 2;
    hero.dir = 1;
    key(' '); run(1); cuts++;
  }
  return cuts;
}
room = 0;
const grassBefore = (() => { let n = 0;
  for (const row of rooms[0]) for (const t of row) if (t === 2) n++;
  return n })();
const cuts = cutAll();
const gems = hero.gems;
/* The shrine takes them - find it wherever it stands. */
let shrine = null;
for (let r = 0; r < 3; r++) for (let ty = 0; ty < GH; ty++)
  for (let tx = 0; tx < GW; tx++)
    if (rooms[r][ty][tx] === 9) shrine = { r: r, tx: tx, ty: ty };
let shrineBought = null;
if (shrine) {
  room = shrine.r;
  const hpBefore = hero.maxhp, gemsBefore = hero.gems;
  hero.hp = 99; hero.swing = 0;
  hero.x = OX + shrine.tx * TILE + TILE / 2 - 20;
  hero.y = OY + shrine.ty * TILE + TILE / 2;
  hero.dir = 1;
  key(' '); run(1);
  shrineBought = { maxhpBefore: hpBefore, maxhpAfter: hero.maxhp,
    gemsBefore: gemsBefore, gemsAfter: hero.gems };
}
console.log(JSON.stringify({
  grass: grassBefore, cuts: cuts, gems: gems, shrine: shrineBought,
}));
"""


def econ_probe(script: str, *, dice: float) -> str:
    """The page's own script, wrapped with the dice loaded to ``dice``.

    ``dice`` above the cut odds (0.99) is the dry run the floor exists
    for; below them (0.0) is the ceiling run where pity never fires.
    """

    return ECON_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "DICE_PLACEHOLDER", repr(dice)
    )


#: What the shrine gives back, purchase by purchase (§5, C-1674).
#:
#: ``creation_gem_sink`` proved gems *leave*; nothing proved anything
#: *arrives*. Here the village is cut bare with the dice loaded to always
#: hit, and the hero touches the shrine until the gems run out. Each
#: touch is recorded whole - the gems before and after, the hearts before
#: and after, the sentence said, the sound rung, the particles thrown -
#: so a payment that buys nothing cannot hide behind a celebration that
#: looks exactly like one that did.
SINK_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(2);
/* The shrine's own voice, overheard. Both are function declarations on
   the page, so wrapping them is how a probe hears what a player hears. */
let heard = [], thrown = 0;
const realSfx = sfx, realBurst = burst;
sfx = function(name){ heard.push(name); return realSfx.apply(null, arguments) };
burst = function(x, y, n){ thrown += (n || 0); return realBurst.apply(null, arguments) };
/* Loaded to always hit: the ceiling run, where the whole village pays. */
rand = () => 0.0;
room = 0;
let cuts = 0;
for (let ty = 0; ty < GH; ty++) for (let tx = 0; tx < GW; tx++) {
  if (rooms[0][ty][tx] !== 2) continue;
  hero.hp = 99; hero.swing = 0;
  hero.x = OX + tx * TILE + TILE / 2 - 20;
  hero.y = OY + ty * TILE + TILE / 2;
  hero.dir = 1;
  key(' '); run(1); cuts++;
}
const purse = hero.gems;
let shrine = null;
for (let r = 0; r < 3; r++) for (let ty = 0; ty < GH; ty++)
  for (let tx = 0; tx < GW; tx++)
    if (rooms[r][ty][tx] === 9) shrine = { r: r, tx: tx, ty: ty };
const buys = [];
if (shrine) {
  room = shrine.r;
  for (let i = 0; i < TOUCHES_PLACEHOLDER; i++) {
    const gems0 = hero.gems, hearts0 = hero.maxhp;
    /* A sentence from an earlier touch is not this touch's answer. */
    heard = []; thrown = 0; msg = null;
    hero.hp = 99; hero.swing = 0;
    hero.x = OX + shrine.tx * TILE + TILE / 2 - 20;
    hero.y = OY + shrine.ty * TILE + TILE / 2;
    hero.dir = 1;
    key(' '); run(1);
    buys.push({ gemsBefore: gems0, gemsAfter: hero.gems,
      heartsBefore: hearts0, heartsAfter: hero.maxhp,
      said: typeof msg === 'string' ? msg : null,
      heard: heard.slice(), thrown: thrown });
  }
}
console.log(JSON.stringify({ cuts: cuts, purse: purse,
  shrine: shrine !== null, buys: buys }));
"""


def sink_probe(script: str, *, touches: int = 5) -> str:
    """The page's own script, wrapped so the shrine can be paid repeatedly.

    ``touches`` is how many times the hero walks into it; the default is
    more than the purse can afford, so the run reaches both the ceiling
    and the empty pocket.
    """

    return SINK_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "TOUCHES_PLACEHOLDER", str(int(touches))
    )


#: One blow on the guardian, and the sixty frames after it (§6 観察 2,
#: C-1343): the flash must stand, the smoke must outlive it, and the
#: smoke must clear - three beats, read off guardFacts frame by frame.
BEAT_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
key(' '); run(2);
room = 2; hero.hp = 99; hero.key = true;
/* One blow, landed for real. */
hero.x = guard.x - 26; hero.y = guard.y; hero.dir = 1; hero.swing = 0;
key(' '); run(1);
const atHit = { hurt: guardFacts().hurt, smoke: guardFacts().smoke };
let hurtFrames = 0, smokeFrames = 0, smokeAfterFlash = 0;
for (let i = 0; i < 60; i++) {
  hero.hp = 99; hero.x = OX + 6 * TILE; hero.y = OY + 2 * TILE;
  run(1);
  const g = guardFacts();
  if (g.hurt > 0) hurtFrames++;
  if (g.smoke > 0) smokeFrames++;
  if (g.smoke > 0 && g.hurt === 0) smokeAfterFlash++;
}
console.log(JSON.stringify({
  hurtAtHit: atHit.hurt, smokeAtHit: atHit.smoke,
  hurtFrames: hurtFrames, smokeFrames: smokeFrames,
  smokeAfterFlash: smokeAfterFlash,
  smokeLeft: guardFacts().smoke,
}));
"""


def beat_probe(script: str) -> str:
    """The page's own script, wrapped so a blow's three beats can be read."""

    return BEAT_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The milestone voices, as wired (§2, C-1346): the shrine's bigger heart
#: and the charm's one-time life are POWERS and must ring the vibrato
#: voice; the key on the ground is a LOCK's item and must stay plain. The
#: AudioContext is the Recorder from the audio probe - connections, not
#: constructions - and each site is driven for real.
MILESTONE_PROBE = KEY_EVENT_JS + """
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
key(' '); run(2);
function findTile(r, code){ let at = null;
  rooms[r].forEach((row, y) => row.forEach((t, x) => { if (t === code) at = [x, y] }));
  return at }
function strike(r, tx, ty){ room = r;
  hero.x = OX + tx * TILE + 16; hero.y = OY + (ty + 1) * TILE + 16;
  hero.dir = 0; hero.swing = 0; hero.queued = false; swing() }
/* The shrine, paid for real. */
hero.gems = 3;
const shrineAt = findTile(0, 9);
nodes.length = 0; strike(0, shrineAt[0], shrineAt[1]);
const shrineNodes = nodes.slice(), heartsAfter = hero.maxhp;
/* The charm, walked onto. */
const charmAt = findTile(1, 11);
room = 1; hero.x = OX + charmAt[0] * TILE + 16; hero.y = OY + charmAt[1] * TILE + 16;
nodes.length = 0; moveHero();
const charmNodes = nodes.slice(), charmHeld = hero.charm;
/* The key on the ground - a lock's item, the control. */
keyDrop = { x: OX + 5 * TILE, y: OY + 5 * TILE };
hero.x = keyDrop.x; hero.y = keyDrop.y;
nodes.length = 0; moveHero();
const keyNodes = nodes.slice(), keyHeld = hero.key;
console.log(JSON.stringify({
  shrineNodes: shrineNodes, heartsAfter: heartsAfter,
  charmNodes: charmNodes, charmHeld: charmHeld,
  keyNodes: keyNodes, keyHeld: keyHeld,
}));
"""


def milestone_probe(script: str) -> str:
    """The page's own script, wrapped so the milestone voices can be heard."""

    return MILESTONE_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The knowledge key, driven (§3, C-1340). The probe learns the order the
#: way a player does - by striking the stone and READING what it says -
#: because the knowledge lives in the world, not in a facts function.
#: Then it knocks wrong on purpose, knocks right, and watches the key
#: fall with the cave's enemies still standing.
KNOW_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.requestAnimationFrame = () => 0;
globalThis.addEventListener = () => {};
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
SCRIPT_PLACEHOLDER
function findTile(r, code){ let at = null;
  rooms[r].forEach((row, y) => row.forEach((t, x) => { if (t === code) at = [x, y] }));
  return at }
function strike(r, tx, ty){ room = r;
  hero.x = OX + tx * TILE + 16; hero.y = OY + (ty + 1) * TILE + 16;
  hero.dir = 0; hero.swing = 0; hero.queued = false; swing() }
/* Read the stone the way a player does. */
const sign = findTile(0, 12);
strike(0, sign[0], sign[1]);
const signMsg = msg;
const names = (signMsg.match(/「(.+) の順に/) || [null, ''])[1].split('→');
const order = names.map(n => KMARKS.indexOf(n));
/* A stone that does not speak is a finding, not a crash: report what it
   said and stop, so the judge can name the silence. */
if (order.length !== 3 || order.some(m => m < 0)) {
  console.log(JSON.stringify({ signMsg: signMsg, order: [] }));
} else {
  const stones = [findTile(1, 13), findTile(1, 14), findTile(1, 15)];
  /* Wrong on purpose: the second mark first must not advance a fresh seal. */
  strike(1, stones[order[1]][0], stones[order[1]][1]);
  const wrongProgress = knowFacts().progress, wrongDrop = !!keyDrop;
  const aliveBefore = enemies[1].filter(e => e.alive).length;
  /* Then right, and the key falls without a fight. */
  order.forEach(m => strike(1, stones[m][0], stones[m][1]));
  const solved = knowFacts().solved, dropped = !!keyDrop;
  const aliveAtSolve = enemies[1].filter(e => e.alive).length;
  moveHero();
  console.log(JSON.stringify({
    signMsg: signMsg, order: order,
    wrongProgress: wrongProgress, wrongDrop: wrongDrop,
    aliveBefore: aliveBefore, aliveAtSolve: aliveAtSolve,
    solved: solved, dropped: dropped, keyGained: hero.key,
  }));
}
"""


def know_probe(script: str) -> str:
    """The page's own script, wrapped so the stone can be read and knocked."""

    return KNOW_PROBE.replace("SCRIPT_PLACEHOLDER", script)


def world_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, stubbed enough to run once, then reported."""

    return WORLD_PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "SCRIPT_PLACEHOLDER", script
    )


#: The face, as watched (§1, C-1351): walk each of the four ways on the
#: template's own keys and read where the eyes went; face away and check
#: they are gone; stand still and count the blink. The clock ticks with
#: the frames (C-1348's lesson: a zero-pinned performance.now freezes the
#: wall-clock FRAME and the blink never comes).
ADV_FACE_PROBE = KEY_EVENT_JS + """
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
  const e = probeKey(k);
  (handlers[type] || []).forEach(fn => fn(e));
}
ev('keydown', ' '); ev('keyup', ' ');
run(2);
/* Each way in turn, on held arrows - the template reads lowercase key
   state every frame, so a hold is one keydown and a later keyup. */
function walk(k){ ev('keydown', k); run(6); const f = faceFacts(); ev('keyup', k); return f }
const right = walk('ArrowRight');
const left = walk('ArrowLeft');
const down = walk('ArrowDown');
const up = walk('ArrowUp');
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
/* Facing sideways: this template hides the face when the hero looks
   away from the camera (faceFacts().shown is dir!==0). */
hero.dir = 1;
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
  right: right, left: left, down: down, up: up,
  blinkFrames: blinkFrames, longestBlink: longest,
}));
"""


def adv_face_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so the hero's face can be watched."""

    return ADV_FACE_PROBE.replace(
        "REDUCED_INPUT", "true" if reduced else "false"
    ).replace("SCRIPT_PLACEHOLDER", script)



#: The maze's ear (§2 増築, C-1630). Two roamers are placed on opposite
#: sides of the same room and cut down with the page's own ``swing()``,
#: and the panner values are read off the audio graph the page really
#: built. The blade's own x is what the sword is heard at, so the hero
#: standing 20px to the left of the target is a reading the hero's own
#: position could not produce.
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
/* Everything so far - the start, the room's name - is positionless. */
const before = pans.length;
/* Each call tagged with the panner it built, so "the sword" and "the
   roamer" are told apart rather than counted together. */
const calls = [];
const realSfx = sfx;
sfx = function(name, pitch, at){ const was = pans.length;
  const out = realSfx.call(this, name, pitch, at);
  calls.push({ name: String(name), pan: pans.length > was ? pans[pans.length - 1] : null });
  return out };
const PW = 720;
/* Facing right with the hero 20px short of the target: the blade lands on
   the roamer, and the hero's own x is a different number from the blade's.
   The blade's tile is cleared first so the swing does not also cut grass
   and add a sound nobody asked about. */
function strike(ex){
  const ty = 4, tx = Math.round((ex - OX - 8) / TILE);
  rooms[room][ty][tx] = 0;
  hero.x = ex - 20; hero.y = OY + ty * TILE + 8; hero.dir = 1;
  hero.swing = 0; hero.queued = false;
  enemies[room] = [{ x: ex, y: hero.y, dx: 0, dy: 0, t: 0, alive: true }];
  const at = calls.length;
  swing();
  return calls.slice(at);
}
const leftHit = strike(OX + 2 * TILE + 8);
const rightHit = strike(OX + 16 * TILE + 8);
/* A sound with no place - played by THE PAGE, not by this probe. Calling
   sfx('step') from here would only prove the probe can call it; swinging
   at a tablet makes the page read it out through its own line. */
function readTablet(){
  const ty = 4, tx = 8;
  rooms[room][ty][tx] = 12;
  hero.x = OX + tx * TILE + 8 - 20; hero.y = OY + ty * TILE + 8; hero.dir = 1;
  hero.swing = 0; hero.queued = false;
  enemies[room] = [];
  const at = calls.length;
  swing();
  return calls.slice(at).filter(c => c.name !== 'sword');
}
const quiet = readTablet();
/* Four from the two blows (the blade and the roamer each side), and the
   fifth from the blade that taps the tablet - the sword still has a
   place even when what it strikes has nothing to say from anywhere. */
const expected = [OX + 2 * TILE + 8, OX + 2 * TILE + 8,
  OX + 16 * TILE + 8, OX + 16 * TILE + 8, OX + 8 * TILE + 8]
  .map(x => (x / PW * 2 - 1) * 0.8);
console.log(JSON.stringify({ before: before, pans: pans, expected: expected,
  left: leftHit, right: rightHit, quiet: quiet }));
"""


def pan_probe(script: str) -> str:
    """The page's own script, wrapped so a blow's stereo place can be read."""

    return PAN_PROBE.replace("SCRIPT_PLACEHOLDER", script)

__all__ = [
    "PAN_PROBE",
    "pan_probe",
    "SAY_PROBE",
    "say_probe",
    "ADVENTURE_DIFFICULTY",
    "ADVENTURE_HOW",
    "ADVENTURE_SCRIPT",
    "ADVENTURE_TITLE",
    "ADVENTURE_WORDS",
    "ADV_FACE_PROBE",
    "adv_face_probe",
    "COMBO_PROBE",
    "CHARM_PROBE",
    "charm_probe",
    "BEAT_PROBE",
    "GUARD_PROBE",
    "RUN_PROBE",
    "run_probe",
    "KNOW_PROBE",
    "MILESTONE_PROBE",
    "beat_probe",
    "milestone_probe",
    "combo_probe",
    "WORLD_PROBE",
    "WRECK_PROBE",
    "wreck_probe",
    "ECON_PROBE",
    "econ_probe",
    "HURT_PROBE",
    "hurt_probe",
    "KNOCK_PROBE",
    "knock_probe",
    "SCENE_ORDER_PROBE",
    "scene_order_probe",
    "SQUASH_PROBE",
    "squash_probe",
    "guard_probe",
    "SINK_PROBE",
    "sink_probe",
    "know_probe",
    "world_probe",
]
