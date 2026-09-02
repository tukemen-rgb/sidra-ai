"""The puzzle template - C-1013's other half, and the last standing apology.

「パズルゲームを作って」 was the request the honesty machinery was still
answering with "that shape is not buildable yet". SameGame is the right first
puzzle for this generator: the rules fit in a paragraph, the board comes
entirely from a seed, and the interesting decision - which group to take
first, since taking one collapses the others - is present in the smallest
version. A sliding puzzle would have been easier and would have had no
decision in it worth making twice.

What keeps it honest as a *puzzle* rather than a clicker: a group is only
poppable at two or more, the board collapses down and then left, and the
game ends when no group of two remains. The end screen says whether the
board was cleared, because "no moves left" and "solved" are different
outcomes and a page that congratulated both would be the same class of lie
the summary guard exists to prevent.

Token contract, shared with every template: ``SPEED_TOKEN`` is how many
colours are in play (fewer is easier), ``BAND_TOKEN`` the board width,
``SEED_TOKEN`` the layout. ``REDUCED``/``FRAME`` come from the animation
preamble - the cursor's pulse freezes, the puzzle does not - and
``sfx``/``shake``/``hitstop``/``burst`` from the audio and juice preambles.
"""

from __future__ import annotations

#: Words that pick this template.
PUZZLE_WORDS: tuple[str, ...] = (
    "パズル",
    "さめがめ",
    "ぷよ",
    "消しゲーム",
    "puzzle",
    "match",
    "samegame",
)

#: (colours in play, board width in cells).
PUZZLE_DIFFICULTY: dict[str, tuple[float, float]] = {
    "easy": (3, 10),
    "normal": (4, 12),
    "hard": (5, 14),
}

PUZZLE_TITLE = "つながり消し"
PUZZLE_HOW = (
    "← ↑ → ↓ でカーソル移動、SPACE で同じ色のかたまりを消す（2 個以上）。"
    "大きいかたまりほど高得点。R でやり直し、M で消音。"
)

PUZZLE_SCRIPT = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const COLOURS=SPEED_TOKEN,COLS=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
const ROWS=8,CELL=Math.min(30,Math.floor((cv.height-70)/ROWS));
const OX=Math.round((cv.width-COLS*CELL)/2),OY=44;
const PALETTE=['CYAN_TOKEN','MAGENTA_TOKEN','#e8c46a','#7fd18a','#9a8cf0'];
let grid,cur,score,state,cleared;
function reset(){rs=(SEED>>>0)||1;grid=[];score=0;state='play';cleared=false;
  cur={x:0,y:0};
  for(let y=0;y<ROWS;y++){const row=[];
    for(let x=0;x<COLS;x++){row.push(Math.floor(rand()*COLOURS))}grid.push(row)}}
/* Flood fill on colour, four-connected. Returns the cells, so the caller can
   both judge the move and know where to throw particles. */
function group(x,y){const c=grid[y][x];if(c<0)return [];
  const seen={},stack=[[x,y]],out=[];
  while(stack.length){const [px,py]=stack.pop();
    if(px<0||py<0||px>=COLS||py>=ROWS)continue;
    const k=px+','+py;if(seen[k])continue;
    if(grid[py][px]!==c)continue;
    seen[k]=1;out.push([px,py]);
    stack.push([px+1,py],[px-1,py],[px,py+1],[px,py-1])}
  return out}
/* Down, then left: the two collapses are what make an early move change
   every later one. */
function collapse(){
  for(let x=0;x<COLS;x++){const col=[];
    for(let y=ROWS-1;y>=0;y--){if(grid[y][x]>=0)col.push(grid[y][x])}
    for(let y=ROWS-1,i=0;y>=0;y--,i++){grid[y][x]=i<col.length?col[i]:-1}}
  let write=0;
  for(let x=0;x<COLS;x++){let full=false;
    for(let y=0;y<ROWS;y++){if(grid[y][x]>=0)full=true}
    if(full){if(write!==x){for(let y=0;y<ROWS;y++){grid[y][write]=grid[y][x];
      grid[y][x]=-1}}write++}}}
function movesLeft(){for(let y=0;y<ROWS;y++){for(let x=0;x<COLS;x++){
  if(grid[y][x]>=0&&group(x,y).length>1)return true}}return false}
function pop(){if(state!=='play')return;
  const cells=group(cur.x,cur.y);
  if(cells.length<2){sfx('clash');shake(1.5);return}
  /* Squared scoring: the reason to look for the big group instead of the
     nearest one. */
  score+=cells.length*cells.length;
  cells.forEach(([x,y])=>{burst(OX+x*CELL+CELL/2,OY+y*CELL+CELL/2,4,
    PALETTE[grid[y][x]]||'CYAN_TOKEN');grid[y][x]=-1});
  sfx('gem');shake(Math.min(9,cells.length));hitstop(cells.length>4?3:1);
  collapse();
  if(!movesLeft()){state='over';
    cleared=grid.every(r=>r.every(v=>v<0));
    /* Clearing the board is a win; running out of moves is the loss the
       beat is for. */
    if(cleared){sfx('win')}else{failBeat(cv.width/2,cv.height/2)}}}
const keys={};
addEventListener('keydown',e=>{keys[e.key.toLowerCase()]=true;
  if(e.code==='Space'){e.preventDefault();
    if(state==='play'){pop()}else{reset()}return}
  if(e.key==='r'||e.key==='R'){reset();return}
  if(state!=='play')return;
  if(e.key==='ArrowLeft'){cur.x=Math.max(0,cur.x-1)}
  if(e.key==='ArrowRight'){cur.x=Math.min(COLS-1,cur.x+1)}
  if(e.key==='ArrowUp'){cur.y=Math.max(0,cur.y-1)}
  if(e.key==='ArrowDown'){cur.y=Math.min(ROWS-1,cur.y+1)}});
addEventListener('keyup',e=>{keys[e.key.toLowerCase()]=false});
cv.addEventListener('pointerdown',e=>{if(state!=='play'){reset();return}
  const r=cv.getBoundingClientRect();
  const x=Math.floor(((e.clientX-r.left)*(cv.width/r.width)-OX)/CELL);
  const y=Math.floor(((e.clientY-r.top)*(cv.height/r.height)-OY)/CELL);
  if(x>=0&&y>=0&&x<COLS&&y<ROWS){cur={x:x,y:y};pop()}});
function draw(now){
  cx.fillStyle='SURFACE_TOKEN';cx.fillRect(0,0,cv.width,cv.height);
  for(let y=0;y<ROWS;y++){for(let x=0;x<COLS;x++){const v=grid[y][x];
    if(v<0)continue;
    const px=OX+x*CELL,py=OY+y*CELL;
    cx.fillStyle=PALETTE[v]||'CYAN_TOKEN';
    cx.fillRect(px+1,py+1,CELL-2,CELL-2);
    /* Shape as well as colour (C-1018): each colour carries its own pip
       count, so the board is readable without telling them apart by hue. */
    cx.fillStyle='#05070f88';
    for(let i=0;i<=v;i++){cx.fillRect(px+4+i*5,py+CELL-7,3,3)}}}
  const pulse=REDUCED?0:FRAME(2,6,now);
  cx.strokeStyle='#dfe7f5';cx.lineWidth=2+pulse;
  cx.strokeRect(OX+cur.x*CELL+0.5,OY+cur.y*CELL+0.5,CELL-1,CELL-1);
  cx.lineWidth=1;
  cx.fillStyle='#dfe7f5';cx.font='13px ui-monospace,monospace';
  cx.fillText('得点 '+score,OX,26);
  const left=group(cur.x,cur.y).length;
  cx.fillText(left>1?('このかたまり '+left+' 個'):'ここは消せない',OX+120,26);
  if(state==='over'){cx.fillStyle='#05070fd0';
    cx.fillRect(0,0,cv.width,cv.height);
    cx.fillStyle='#dfe7f5';cx.font='20px ui-monospace,monospace';
    const a=cleared?'全部消えた。':'もう消せる手がない。';
    cx.fillText(a,cv.width/2-a.length*10,cv.height/2-8);
    cx.font='13px ui-monospace,monospace';
    const b='得点 '+score+' / SPACE か R でもう一度';
    cx.fillText(b,cv.width/2-b.length*6.5,cv.height/2+18)}}
function step(){draw(performance.now());requestAnimationFrame(step)}
reset();step();
"""

__all__ = [
    "PUZZLE_DIFFICULTY",
    "PUZZLE_HOW",
    "PUZZLE_SCRIPT",
    "PUZZLE_TITLE",
    "PUZZLE_WORDS",
]
