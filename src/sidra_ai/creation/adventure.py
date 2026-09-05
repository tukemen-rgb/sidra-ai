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
const NAMES=['森のはずれ','ひかり苔の洞窟','風の祭壇'];
let rooms=[],enemies=[],room=0,msg='',msgT=0,guard=null;
let hero={x:0,y:0,dir:2,hp:3,gems:0,key:false,swing:0,inv:0};
let state='play';let keyDrop=null;let FIRSTCUT=true;
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
  const cave=empty();carve(cave,1,10);cave[0][6]=4;cave[0][13]=4;
  cave[4][0]=6;cave[4][GW-1]=5;
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
    mode:'stride',wind:0,chg:0,dx:0,dy:0,inv:0,t:70,step:0};
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
function reset(){rs=(SEED>>>0)||1;build();room=0;keyDrop=null;state='play';FIRSTCUT=true;
  hero={x:OX+2*TILE,y:OY+4*TILE,dir:2,hp:3,maxhp:3,gems:0,key:false,
    charm:false,swing:0,inv:0};
  say('ぼうしの勇者、めざめる。')}
function say(t){msg=t;msgT=140}
function tileAt(px,py){const x=Math.floor((px-OX)/TILE),y=Math.floor((py-OY)/TILE);
  if(x<0||y<0||x>=GW||y>=GH)return 1;return rooms[room][y][x]}
function solid(px,py){const t=tileAt(px,py);
  return t===1||t===2||t===3||t===4||t===7||t===8||t===9||t===10}
const keys={};
addEventListener('keydown',e=>{keys[e.key.toLowerCase()]=true;
  if(e.code==='Space'){e.preventDefault();swing()}
  if(e.key==='r'||e.key==='R'){if(state!=='play')reset()}});
addEventListener('keyup',e=>{keys[e.key.toLowerCase()]=false});
cv.addEventListener('pointerdown',()=>{if(state==='play'){swing()}else{reset()}});
function swing(){if(state!=='play')return;
  /* A press during the swing is kept, not dropped (§12, C-1311): one
     queued blow, fired the frame the arm is free. Mashing becomes a
     steady fastest-possible rhythm instead of a lottery. */
  if(hero.swing>0){hero.queued=true;return}
  hero.swing=10;sfx('sword');
  const fx=hero.x+[0,16,0,-16][hero.dir]*1.25,fy=hero.y+[-16,0,16,0][hero.dir]*1.25;
  const tx=Math.floor((fx-OX)/TILE),ty=Math.floor((fy-OY)/TILE);
  if(ty>=0&&ty<GH&&tx>=0&&tx<GW){
    const t=rooms[room][ty][tx];
    if(t===2){rooms[room][ty][tx]=0;sfx('cut');
      burst(OX+tx*TILE+TILE/2,OY+ty*TILE+TILE/2,10,'ACCENT_JUICE');
      /* The first cut always pays. After that the odds are the odds -
         what §8 asks for is a first success, not an easier game. */
      if(FIRSTCUT||rand()<0.34){FIRSTCUT=false;
        hero.gems++;say('草のかげに宝石があった。');sfx('gem');
        burst(OX+tx*TILE+TILE/2,OY+ty*TILE+TILE/2,14,'ALERT_JUICE')}}
    /* The boss stands behind the boss key (§3): the key alone is only half
       the lock while the guardian is on its feet. */
    if(t===7){if(!hero.key){say('鍵がかかっている。洞窟の敵が持っているらしい。');sfx('clash')}
      else if(guard&&guard.alive){say('番人が生きている限り、宝箱は開かない。');sfx('clash')}
      else{state='win';winBeat(hero.x,hero.y)}}
    if(t===8){say('「東の洞窟の敵が鍵を守っている。祭壇の宝を頼む。」');sfx('step')}
    /* The sink (§5): gems were a tap with no outlet, so cutting grass paid
       in a number. Three of them buy a heart, which is what makes the
       grass worth cutting. */
    if(t===9){if(hero.gems>=3){hero.gems-=3;hero.maxhp=Math.min(5,hero.maxhp+1);
        hero.hp=hero.maxhp;say('祠が宝石を受け取った。ハートが増えた。');sfx('key');
        burst(OX+tx*TILE+TILE/2,OY+ty*TILE+TILE/2,18,'ALERT_JUICE')}
      else{say('祠は宝石を 3 個ほしがっている（いま '+hero.gems+' 個）。');sfx('clash')}}
    /* The optional door (§3): the run is winnable without ever opening it. */
    if(t===10){if(hero.gems>=2){hero.gems-=2;rooms[room][ty][tx]=0;
        say('わき道が開いた。');sfx('key')}
      else{say('宝石 2 個で開きそうだ（いま '+hero.gems+' 個）。');sfx('clash')}}}
  enemies[room].forEach(en=>{if(!en.alive)return;
    if(Math.hypot(en.x-fx,en.y-fy)<22){en.alive=false;sfx('hurt');
      shake(6);hitstop(3);burst(en.x,en.y,16,'ALERT_JUICE');
      if(room===1&&enemies[1].every(e=>!e.alive)){keyDrop={x:en.x,y:en.y}}}});
  /* The guardian takes a blade with weight: thirty frames of armour after
     each hit, so mashing lands one blow, not six. Half health turns the
     page to phase 2 (§6 観察 3). */
  if(room===2&&guard&&guard.alive&&guard.inv<=0&&Math.hypot(guard.x-fx,guard.y-fy)<30){
    guard.hp--;guard.inv=30;sfx('hurt');shake(8);hitstop(4);
    burst(guard.x,guard.y,16,'ALERT_JUICE');
    guard.x+=[0,12,0,-12][hero.dir];guard.y+=[-12,0,12,0][hero.dir];
    if(guard.hp<=0){guard.alive=false;sfx('win');shake(12);hitstop(6);
      burst(guard.x,guard.y,32,'ALERT_JUICE');
      say('番人は崩れ落ちた。祭壇が静まりかえる。')}
    else if(guard.hp===3){say('番人の足が速くなった。');sfx('charge')}}}
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
    say('護符を見つけた。一度だけ身代わりになる。');sfx('key');
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
  if(hero.inv<=0&&d<16){hero.hp--;hero.inv=60;sfx('hurt');
    shake(9);hitstop(4);burst(hero.x,hero.y,12,'ALERT_JUICE');
    hero.x-=en.dx*14;hero.y-=en.dy*14;
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
    hero.hp--;hero.inv=60;sfx('hurt');shake(10);hitstop(5);
    burst(hero.x,hero.y,14,'ALERT_JUICE');
    hero.x+=(hero.x-guard.x)/d*20;hero.y+=(hero.y-guard.y)/d*20;
    if(hero.hp<=0){if(!charmSave()){state='over';failBeat(hero.x,hero.y)}}
    else{say('重い一撃。')}}}
function guardFacts(){return guard?{alive:guard.alive,hp:guard.hp,max:guard.max,
  mode:guard.mode,wind:guard.wind,x:guard.x,y:guard.y,inv:guard.inv,
  speed:guardSpeed(),windFrames:guardWind(),
  phase:guard.hp<=3?2:1}:null}
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
  if(t===11){cx.fillStyle='ALERT_JUICE';diamond(x+TILE/2,y+TILE/2,8);cx.fill()}}
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
  enemies[room].forEach(en=>{if(!en.alive)return;
    const bob=[0,-2,0,2][FRAME(4,9,now)];
    sprite('enemy',en.x-10,en.y-10+bob,20,20,'MAGENTA_TOKEN')});
  if(room===2&&guard&&guard.alive){
    /* Twice the hero's size, on a slower beat than any small enemy - the
       weight is the stride (§6 観察 2). The wind-up is the held flash
       beat; under reduced motion the same warning is a steady outline. */
    const gb=[0,-1,0,1][FRAME(4,13,now)];
    const winding=guard.mode==='wind';
    cx.fillStyle=(winding&&!REDUCED&&FRAME(2,4,now)===0)?'#dfe7f5':'MAGENTA_TOKEN';
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
    for(let i=0;i<guard.max;i++){cx.strokeStyle='#dfe7f5';
      cx.strokeRect(guard.x-19.5+i*6.5,guard.y-37.5,5,5)}
    cx.fillStyle='#dfe7f5';
    for(let i=0;i<guard.hp;i++){cx.fillRect(guard.x-19+i*6.5,guard.y-37,4,4)}}
  if(!(hero.inv>0&&FRAME(2,3,now)===1)){
    sprite('hero',hero.x-10,hero.y-8,20,18,'CYAN_TOKEN');
    cx.fillStyle='#0a2a33';cx.fillRect(hero.x-11,hero.y-14,22,7)}
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
    '宝石 '+hero.gems+' 個 / 護符 '+(hero.charm?'あり':'なし')+' / R か タップでもう一度')}
  if(state==='over'){shade('ちからつきた。','R か タップでやり直す')}}
function glow(x,y,r,now){const g=cx.createRadialGradient(x,y,4,x,y,r);
  g.addColorStop(0,'#f5d89a55');g.addColorStop(1,'#00000000');
  cx.fillStyle=g;cx.fillRect(x-r,y-r,r*2,r*2)}
function shade(a,b){cx.fillStyle='SCRIM_TOKEN'+'d0';cx.fillRect(0,0,cv.width,cv.height);
  cx.fillStyle='INK_TOKEN';cx.font='20px ui-monospace,monospace';
  cx.fillText(a,cv.width/2-a.length*10,cv.height/2-8);
  cx.font='13px ui-monospace,monospace';
  cx.fillText(b,cv.width/2-b.length*6.5,cv.height/2+18)}
function step(){const now=performance.now();
  /* Only fighting when something is actually near: the quiet stretches of a
     dungeon are what make the loud ones read as loud (§6 観察 4). */
  combat(state==='play'&&gateState()==='playing'&&
    ((enemies[room]||[]).some(e=>e.alive&&Math.hypot(e.x-hero.x,e.y-hero.y)<120)
     ||(room===2&&guard!==null&&guard.alive&&Math.hypot(guard.x-hero.x,guard.y-hero.y)<160)));
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
COMBO_PROBE = """
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
CHARM_PROBE = """
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


GUARD_PROBE = """
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
}));
"""


def guard_probe(script: str) -> str:
    """The page's own script, wrapped so the guardian can be fought."""

    return GUARD_PROBE.replace("SCRIPT_PLACEHOLDER", script)


def world_probe(script: str, *, reduced: bool = False) -> str:
    """The page's own script, stubbed enough to run once, then reported."""

    return WORLD_PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "SCRIPT_PLACEHOLDER", script
    )


__all__ = [
    "ADVENTURE_DIFFICULTY",
    "ADVENTURE_HOW",
    "ADVENTURE_SCRIPT",
    "ADVENTURE_TITLE",
    "ADVENTURE_WORDS",
    "COMBO_PROBE",
    "CHARM_PROBE",
    "charm_probe",
    "GUARD_PROBE",
    "combo_probe",
    "WORLD_PROBE",
    "guard_probe",
    "world_probe",
]
