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
/* seeded LCG: the layout is a promise (same request, same world), and the
   enemies keep drawing from it so a run is reproducible too */
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const NAMES=['森のはずれ','ひかり苔の洞窟','風の祭壇'];
let rooms=[],enemies=[],room=0,msg='',msgT=0;
let hero={x:0,y:0,dir:2,hp:3,gems:0,key:false,swing:0,inv:0};
let state='play';let keyDrop=null;
function empty(){const m=[];for(let y=0;y<GH;y++){const r=[];
  for(let x=0;x<GW;x++){r.push(x===0||y===0||x===GW-1||y===GH-1?1:0)}m.push(r)}return m}
function carve(m,code,n){let put=0;while(put<n){const x=2+Math.floor(rand()*(GW-4)),
  y=2+Math.floor(rand()*(GH-4));if(m[y][x]===0){m[y][x]=code;put++}}}
function build(){
  const forest=empty();carve(forest,2,14);forest[3][3]=8;forest[4][GW-1]=5;
  const cave=empty();carve(cave,1,10);cave[0][6]=4;cave[0][13]=4;
  cave[4][0]=6;cave[4][GW-1]=5;
  const altar=empty();carve(altar,1,6);altar[4][0]=6;altar[4][10]=7;
  rooms=[forest,cave,altar];
  enemies=[[],[],[]];
  for(let i=0;i<ECOUNT;i++){enemies[1].push(spawn(1))}
  for(let i=0;i<Math.max(1,ECOUNT-1);i++){enemies[2].push(spawn(2))}
}
function spawn(r){let x,y;do{x=2+Math.floor(rand()*(GW-4));
  y=2+Math.floor(rand()*(GH-4))}while(rooms[r][y][x]!==0||(r===2&&x>7&&x<13));
  return {x:OX+x*TILE+8,y:OY+y*TILE+8,dx:0,dy:0,t:0,alive:true}}
function reset(){rs=(SEED>>>0)||1;build();room=0;keyDrop=null;state='play';
  hero={x:OX+2*TILE,y:OY+4*TILE,dir:2,hp:3,gems:0,key:false,swing:0,inv:0};
  say('ぼうしの勇者、めざめる。')}
function say(t){msg=t;msgT=140}
function tileAt(px,py){const x=Math.floor((px-OX)/TILE),y=Math.floor((py-OY)/TILE);
  if(x<0||y<0||x>=GW||y>=GH)return 1;return rooms[room][y][x]}
function solid(px,py){const t=tileAt(px,py);return t===1||t===2||t===3||t===4||t===7||t===8}
const keys={};
addEventListener('keydown',e=>{keys[e.key.toLowerCase()]=true;
  if(e.code==='Space'){e.preventDefault();swing()}
  if(e.key==='r'||e.key==='R'){if(state!=='play')reset()}});
addEventListener('keyup',e=>{keys[e.key.toLowerCase()]=false});
cv.addEventListener('pointerdown',()=>{if(state==='play'){swing()}else{reset()}});
function swing(){if(state!=='play'||hero.swing>0)return;hero.swing=10;sfx('sword');
  const fx=hero.x+[0,16,0,-16][hero.dir]*1.6,fy=hero.y+[-16,0,16,0][hero.dir]*1.6;
  const tx=Math.floor((fx-OX)/TILE),ty=Math.floor((fy-OY)/TILE);
  if(ty>=0&&ty<GH&&tx>=0&&tx<GW){
    const t=rooms[room][ty][tx];
    if(t===2){rooms[room][ty][tx]=0;sfx('cut');
      if(rand()<0.34){hero.gems++;say('草のかげに宝石があった。');sfx('gem')}}
    if(t===7){if(hero.key){state='win';sfx('win')}else{say('鍵がかかっている。洞窟の敵が持っているらしい。');sfx('clash')}}
    if(t===8){say('「東の洞窟の敵が鍵を守っている。祭壇の宝を頼む。」');sfx('step')}}
  enemies[room].forEach(en=>{if(!en.alive)return;
    if(Math.hypot(en.x-fx,en.y-fy)<26){en.alive=false;sfx('hurt');
      if(room===1&&enemies[1].every(e=>!e.alive)){keyDrop={x:en.x,y:en.y}}}})}
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
  if(t===5&&room<2){room++;hero.x=OX+TILE+6;say(NAMES[room]);sfx('step')}
  else if(t===6&&room>0){room--;hero.x=OX+(GW-2)*TILE+26;say(NAMES[room]);sfx('step')}
  if(keyDrop&&room===1&&Math.hypot(hero.x-keyDrop.x,hero.y-keyDrop.y)<20){
    hero.key=true;keyDrop=null;say('鍵を手に入れた。');sfx('key')}}
function moveEnemies(){enemies[room].forEach(en=>{if(!en.alive)return;en.t--;
  const d=Math.hypot(hero.x-en.x,hero.y-en.y);
  if(d<TILE*4){en.dx=(hero.x-en.x)/d*ESPEED;en.dy=(hero.y-en.y)/d*ESPEED}
  else if(en.t<=0){const a=rand()*6.28318;
    en.dx=Math.cos(a)*ESPEED*0.6;en.dy=Math.sin(a)*ESPEED*0.6;en.t=50+rand()*60}
  const nx=en.x+en.dx,ny=en.y+en.dy;
  if(!solid(nx,en.y)){en.x=nx}if(!solid(en.x,ny)){en.y=ny}
  if(hero.inv<=0&&d<16){hero.hp--;hero.inv=60;sfx('hurt');
    hero.x-=en.dx*14;hero.y-=en.dy*14;
    if(hero.hp<=0){state='over';sfx('lose')}else{say('いたい。')}}})}
const GROUND={0:'SURFACE_TOKEN',5:'RAISED_TOKEN',6:'RAISED_TOKEN'};
function drawTile(t,x,y,now){
  cx.fillStyle=GROUND[t]||'SURFACE_TOKEN';cx.fillRect(x,y,TILE,TILE);
  if(t===1){sprite('rock',x+2,y+2,TILE-4,TILE-4,'RAISED_TOKEN');
    cx.strokeStyle='#00000033';cx.strokeRect(x+2,y+2,TILE-4,TILE-4)}
  if(t===2){sprite('bush',x+4,y+4,TILE-8,TILE-8,'#2c5a3f')}
  if(t===3){cx.fillStyle='#12405a';cx.fillRect(x,y,TILE,TILE)}
  if(t===4){cx.fillStyle='RAISED_TOKEN';cx.fillRect(x+2,y+2,TILE-4,TILE-4);
    const fl=[3,5,4,6][FRAME(4,7,now)];
    cx.fillStyle='#e8a33d';cx.fillRect(x+12,y+8,8,8+fl)}
  if(t===7){cx.fillStyle='#7a5a2e';cx.fillRect(x+4,y+8,TILE-8,TILE-12);
    cx.fillStyle='CYAN_TOKEN';cx.fillRect(x+13,y+14,6,6)}
  if(t===8){sprite('npc',x+6,y+4,TILE-12,TILE-8,'#c8b28a');
    cx.fillStyle='MAGENTA_TOKEN';cx.fillRect(x+8,y+2,TILE-16,6)}}
function draw(now){
  cx.fillStyle='#05070f';cx.fillRect(0,0,cv.width,cv.height);
  for(let y=0;y<GH;y++){for(let x=0;x<GW;x++){
    drawTile(rooms[room][y][x],OX+x*TILE,OY+y*TILE,now)}}
  if(keyDrop&&room===1){cx.fillStyle='CYAN_TOKEN';
    cx.fillRect(keyDrop.x-4,keyDrop.y-7,8,10);cx.fillRect(keyDrop.x-1,keyDrop.y-1,6,3)}
  enemies[room].forEach(en=>{if(!en.alive)return;
    const bob=[0,-2,0,2][FRAME(4,9,now)];
    sprite('enemy',en.x-10,en.y-10+bob,20,20,'MAGENTA_TOKEN')});
  if(!(hero.inv>0&&FRAME(2,3,now)===1)){
    sprite('hero',hero.x-10,hero.y-8,20,18,'CYAN_TOKEN');
    cx.fillStyle='#0a2a33';cx.fillRect(hero.x-11,hero.y-14,22,7)}
  if(hero.swing>0){const p=ease(hero.swing/10);cx.strokeStyle='#dfe7f5';
    cx.lineWidth=3;cx.beginPath();
    const ang=[[-2.2,-0.9],[-0.7,0.7],[0.9,2.2],[2.4,3.9]][hero.dir];
    cx.arc(hero.x,hero.y,20,ang[0]+p,ang[1]+p);cx.stroke();cx.lineWidth=1}
  if(room===1){cx.fillStyle='#02030a';cx.globalAlpha=REDUCED?0.35:0.35+0.04*FRAME(2,11,now);
    cx.fillRect(0,0,cv.width,cv.height);cx.globalAlpha=1;
    [[6,0],[13,0]].forEach(p=>{glow(OX+p[0]*TILE+16,OY+16,86,now)});
    glow(hero.x,hero.y,64,now)}
  cx.fillStyle='MAGENTA_TOKEN';
  for(let i=0;i<hero.hp;i++){cx.fillRect(OX+i*18,2,14,10)}
  cx.fillStyle='#dfe7f5';cx.font='13px ui-monospace,monospace';
  cx.fillText('宝石 '+hero.gems+(hero.key?'  鍵あり':''),OX+70,11);
  cx.fillText(NAMES[room],cv.width-OX-150,11);
  if(msgT>0){msgT--;cx.fillStyle='#0a0f1cd9';
    cx.fillRect(OX,cv.height-34,GW*TILE,26);cx.fillStyle='#dfe7f5';
    cx.fillText(msg,OX+10,cv.height-16)}
  if(state==='win'){shade('宝箱をあけた。冒険の勝利。','宝石 '+hero.gems+' 個 / R か タップでもう一度')}
  if(state==='over'){shade('ちからつきた。','R か タップでやり直す')}}
function glow(x,y,r,now){const g=cx.createRadialGradient(x,y,4,x,y,r);
  g.addColorStop(0,'#f5d89a55');g.addColorStop(1,'#00000000');
  cx.fillStyle=g;cx.fillRect(x-r,y-r,r*2,r*2)}
function shade(a,b){cx.fillStyle='#05070fd0';cx.fillRect(0,0,cv.width,cv.height);
  cx.fillStyle='#dfe7f5';cx.font='20px ui-monospace,monospace';
  cx.fillText(a,cv.width/2-a.length*10,cv.height/2-8);
  cx.font='13px ui-monospace,monospace';
  cx.fillText(b,cv.width/2-b.length*6.5,cv.height/2+18)}
function step(){const now=performance.now();
  if(state==='play'){if(hero.swing>0)hero.swing--;if(hero.inv>0)hero.inv--;
    moveHero();moveEnemies()}
  draw(now);requestAnimationFrame(step)}
reset();step();
"""

__all__ = [
    "ADVENTURE_DIFFICULTY",
    "ADVENTURE_HOW",
    "ADVENTURE_SCRIPT",
    "ADVENTURE_TITLE",
    "ADVENTURE_WORDS",
]
