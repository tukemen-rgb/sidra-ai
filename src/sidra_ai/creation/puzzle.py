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
The collapse is animated (§1 トゥイーン): the grid is final the frame a
group pops, but each tile keeps a visual offset from its new square that
eases to zero, so the fall is seen instead of teleported - and under
reduced motion no offset is ever written.
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
/* The last sky (§7, C-1327): the round clock is the journey, so the air
   around the board steps once per third of the sixty seconds and the
   final stretch is the brightest. Tiles and pips are information and
   keep their colours (§4); only the backdrop breathes. ROUND_MS is
   played time, so the title screen spends none of it. */
setPal(PUZZLE_PAL_TOKEN);
/* The HUD's own contract (§4 WCAG 1.4.3, C-1329): ink and plate are these
   constants and draw() paints through them, so what hudFacts() reports is
   what the frame shows. The plate is the UNtinted theme surface at 0.7
   over the sky - the same trick the round strips use, in the theme's own
   colours - so the text keeps its designed contrast under the brightest
   final act. The ink is the theme's, not a hardcoded near-white: on the
   light themes that hardcode was 1.0:1, an invisible scoreboard. */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A,cursor:HUD_INK}}
let grid,cur,score,state,cleared,offY,offX,hammers;
/* The board as it stood when it jammed (C-1427). Snapshotted at the
   moment the deadlock is declared rather than recomputed later, so the
   result strip reports the board that ended the go and not whatever a
   later frame happens to hold. Counting only - the game reads none of
   these back. */
let JAM_TILES=0,JAM_HAMMERS=0,JAM_COLOURS=0,JAM_BROKEN=0;
/* The board's economy (§5, C-1322): a pop of HAMMER_EARN or more banks
   one hammer, up to HAMMER_CAP; a hammer breaks one lone tile. Skill is
   converted into survival - the squared score stays vanity, the hammer
   is the currency with a purpose. */
const HAMMER_EARN=5,HAMMER_CAP=3;
function reset(){rs=(SEED>>>0)||1;grid=[];offY=[];offX=[];score=0;state='play';
  cleared=false;cur={x:0,y:0};hammers=0;
  JAM_TILES=0;JAM_HAMMERS=0;JAM_COLOURS=0;JAM_BROKEN=0;
  for(let y=0;y<ROWS;y++){const row=[],oy=[],ox=[];
    for(let x=0;x<COLS;x++){row.push(Math.floor(rand()*COLOURS));
      oy.push(0);ox.push(0)}grid.push(row);offY.push(oy);offX.push(ox)}}
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
   every later one. The LOGIC is still instant - the board below is final
   the frame the group pops - but each move is recorded as a visual offset
   (pixels above / right of the final square) that settle() eases to zero,
   so the fall is seen instead of teleported (§1 トゥイーン). Offsets carry
   through both passes and through chained pops mid-flight; under reduced
   motion no offset is written and the board keeps snapping. */
function collapse(){
  for(let x=0;x<COLS;x++){const col=[];
    for(let y=ROWS-1;y>=0;y--){if(grid[y][x]>=0)col.push(
      {v:grid[y][x],oy:y,rem:offY[y][x]})}
    for(let y=ROWS-1,i=0;y>=0;y--,i++){
      if(i<col.length){grid[y][x]=col[i].v;
        offY[y][x]=REDUCED?0:col[i].rem+(y-col[i].oy)*CELL}
      else{grid[y][x]=-1;offY[y][x]=0}}}
  let write=0;
  for(let x=0;x<COLS;x++){let full=false;
    for(let y=0;y<ROWS;y++){if(grid[y][x]>=0)full=true}
    if(full){if(write!==x){for(let y=0;y<ROWS;y++){grid[y][write]=grid[y][x];
      offY[y][write]=offY[y][x];
      offX[y][write]=REDUCED?0:offX[y][x]+(x-write)*CELL;
      grid[y][x]=-1;offY[y][x]=0;offX[y][x]=0}}write++}}}
/* Exponential ease-out, the identity under reduced motion: ~0.3s from a
   full-board drop to rest, snapped to the grid below half a pixel. */
function settle(){for(let y=0;y<ROWS;y++){for(let x=0;x<COLS;x++){
  offY[y][x]*=0.72;if(offY[y][x]<0.5)offY[y][x]=0;
  offX[y][x]*=0.72;if(offX[y][x]<0.5)offX[y][x]=0}}}
/* A move is a pop *or* a hammer (C-1428). The deadlock check used to
   look only for a group of two, which ended the go while the comeback
   tool was still in the purse - and a hammer is a real move: it breaks a
   lone tile, and the collapse that follows can put two of a colour beside
   each other again. Measured before the fix: a greedy round stranded 17
   tiles while holding 3 unspent hammers. */
function movesLeft(){let any=false;
  for(let y=0;y<ROWS;y++){for(let x=0;x<COLS;x++){
    if(grid[y][x]<0)continue;any=true;
    if(group(x,y).length>1)return true}}
  return any&&hammers>0}
/* What the board looked like at the deadlock. Measured, not assumed:
   every tile still standing when moves run out is a group of one - that
   is what "no moves" means here - so the counts worth keeping are how
   many are stranded, in how many colours, and how much of the comeback
   tool went unspent. */
function jam(){let n=0;const seen={};
  for(let y=0;y<ROWS;y++){for(let x=0;x<COLS;x++){
    if(grid[y][x]<0)continue;n++;seen[grid[y][x]]=1}}
  JAM_TILES=n;JAM_HAMMERS=hammers;JAM_COLOURS=Object.keys(seen).length}
function jamFacts(){return {tiles:JAM_TILES,hammers:JAM_HAMMERS,
  colours:JAM_COLOURS,broken:JAM_BROKEN,cleared:cleared,state:state}}
function pop(){if(state!=='play')return;
  const cells=group(cur.x,cur.y);
  if(cells.length<2){
    /* The sink: one hammer breaks one lone tile - the classic comeback
       tool, bought with an earlier big clear. No points for it (a tool,
       not a score), and at zero hammers the refusal is what it was. */
    if(cells.length===1&&hammers>0){hammers--;JAM_BROKEN++;
      const [[bx,by]]=cells;
      burst(OX+bx*CELL+CELL/2,OY+by*CELL+CELL/2,8,
        PALETTE[grid[by][bx]]||'CYAN_TOKEN');
      grid[by][bx]=-1;sfx('sword');shake(3);hitstop(2);
      collapse();
      if(!movesLeft()){state='over';jam();
        cleared=grid.every(r=>r.every(v=>v<0));
        if(cleared){winBeat(cv.width/2,cv.height/2)}
        else{failBeat(cv.width/2,cv.height/2)}}
      return}
    sfx('clash');shake(1.5);return}
  /* The tap: a big clear pays in the currency that matters, capped so
     hoarding cannot trivialise the endgame (§5 tap/sink balance). */
  if(cells.length>=HAMMER_EARN){hammers=Math.min(HAMMER_CAP,hammers+1);
    sfx('key')}
  /* Squared scoring: the reason to look for the big group instead of the
     nearest one. */
  /* Over the middle of the group that was cleared, so a big clear's
     number appears where the big clear was (C-1418). */
  const popX=OX+CELL/2+CELL*cells.reduce(function(a,c){return a+c[0]},0)/cells.length,
        popY=OY+CELL/2+CELL*cells.reduce(function(a,c){return a+c[1]},0)/cells.length;
  score+=scorePop(popX,popY,cells.length*cells.length);
  cells.forEach(([x,y])=>{burst(OX+x*CELL+CELL/2,OY+y*CELL+CELL/2,4,
    PALETTE[grid[y][x]]||'CYAN_TOKEN');grid[y][x]=-1});
  sfx('gem');shake(Math.min(9,cells.length));hitstop(cells.length>4?3:1);
  collapse();
  if(!movesLeft()){state='over';jam();
    cleared=grid.every(r=>r.every(v=>v<0));
    /* Clearing the board is a win; running out of moves is the loss the
       beat is for. */
    if(cleared){winBeat(cv.width/2,cv.height/2)}else{failBeat(cv.width/2,cv.height/2)}}}
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
  setScene(Math.min(2,ROUND_MS/(ROUND_LIMIT_MS/3)|0));
  cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(0,0,cv.width,cv.height);
  for(let y=0;y<ROWS;y++){for(let x=0;x<COLS;x++){const v=grid[y][x];
    if(v<0)continue;
    const px=OX+x*CELL+offX[y][x],py=OY+y*CELL-offY[y][x];
    cx.fillStyle=PALETTE[v]||'CYAN_TOKEN';
    cx.fillRect(px+1,py+1,CELL-2,CELL-2);
    /* Shape as well as colour (C-1018): each colour carries its own pip
       count, so the board is readable without telling them apart by hue. */
    cx.fillStyle='#05070f88';
    for(let i=0;i<=v;i++){cx.fillRect(px+4+i*5,py+CELL-7,3,3)}}}
  const pulse=REDUCED?0:FRAME(2,6,now);
  /* The cursor is a component, not decoration: it inherits the theme's
     ink like the text does (C-1131 themed the words but not this stroke,
     and the old near-white was 1.0:1 on the light themes). */
  cx.strokeStyle=HUD_INK;cx.lineWidth=2+pulse;
  cx.strokeRect(OX+cur.x*CELL+0.5,OY+cur.y*CELL+0.5,CELL-1,CELL-1);
  cx.lineWidth=1;
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(OX-8,10,336,22);cx.globalAlpha=1;
  cx.fillStyle=HUD_INK;cx.font='13px ui-monospace,monospace';
  cx.fillText('得点 '+score+'  つち ×'+hammers,OX,26);
  const left=group(cur.x,cur.y).length;
  cx.fillText(left>1?('このかたまり '+left+' 個'):'ここは消せない',OX+120,26);
  if(state==='over'){cx.fillStyle='SCRIM_TOKEN'+'d0';
    cx.fillRect(0,0,cv.width,cv.height);
    cx.fillStyle='INK_TOKEN';cx.font='20px ui-monospace,monospace';
    const a=cleared?'全部消えた。':'もう消せる手がない。';
    cx.fillText(a,cv.width/2-a.length*10,cv.height/2-8);
    cx.font='13px ui-monospace,monospace';
    const b='得点 '+score+' / SPACE か R でもう一度';
    cx.fillText(b,cv.width/2-b.length*6.5,cv.height/2+18)}}
function step(){settle();draw(performance.now());requestAnimationFrame(step)}
/* Read back off the running page: how far the board is from rest, and a
   group whose pop is guaranteed to drop something (a member with a foreign
   tile directly above), so a probe measures a real fall, not a lucky one. */
function puzzleFacts(){let mx=0;
  for(let y=0;y<ROWS;y++){for(let x=0;x<COLS;x++){
    mx=Math.max(mx,offY[y][x],offX[y][x])}}
  let tx=-1,ty=-1;
  outer:for(let y=0;y<ROWS;y++){for(let x=0;x<COLS;x++){
    if(grid[y][x]<0)continue;const g=group(x,y);if(g.length<2)continue;
    const k={};g.forEach(c=>{k[c[0]+','+c[1]]=1});
    for(const [gx,gy] of g){if(gy>0&&grid[gy-1][gx]>=0&&!k[gx+','+(gy-1)]){
      tx=x;ty=y;break outer}}}}
  /* The economy, readable (C-1322): the biggest group on the board, one
     lone tile if any, the live tile count and the hammer purse. */
  let bx=-1,by=-1,bn=0,lx=-1,ly=-1,tiles=0;
  for(let y=0;y<ROWS;y++){for(let x=0;x<COLS;x++){
    if(grid[y][x]<0)continue;tiles++;
    const n=group(x,y).length;
    if(n>bn){bn=n;bx=x;by=y}
    if(n===1&&lx<0){lx=x;ly=y}}}
  return {state:state,score:score,moving:mx,scene:SCENE,ms:ROUND_MS,
    cur:{x:cur.x,y:cur.y},target:{x:tx,y:ty},
    hammers:hammers,tiles:tiles,
    best:{x:bx,y:by,n:bn},lone:{x:lx,y:ly}}}
reset();step();
"""

#: The page driven in node: the browser is the same no-op proxy the other
#: template probes build. One guaranteed-to-fall group is popped and the
#: board's distance from rest is read the frame after, then again once the
#: settle should be over - and under reduced motion the same pop must
#: never move at all.
PROBE = """
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
/* Past the briefing gate - the gate press may also reach the template and
   pop at the starting cursor, so the board is given time to come to rest
   before the measured pop. Then walk the cursor onto the falling group. */
key(' ');
run(40);
const before = puzzleFacts();
const t = before.target;
if (t.x >= 0) {
  while (puzzleFacts().cur.x !== t.x) key(puzzleFacts().cur.x < t.x ? 'ArrowRight' : 'ArrowLeft');
  while (puzzleFacts().cur.y !== t.y) key(puzzleFacts().cur.y < t.y ? 'ArrowDown' : 'ArrowUp');
}
key(' ');
const justPopped = puzzleFacts();
run(6);
const midFlight = puzzleFacts();
run(60);
const settled = puzzleFacts();
console.log(JSON.stringify({
  hadTarget: t.x >= 0,
  scoreBefore: before.score, scoreAfter: justPopped.score,
  movingAtPop: justPopped.moving, movingMid: midFlight.moving,
  movingSettled: settled.moving, state: settled.state,
}));
"""


#: The board's economy, played out (§5, C-1322): greedy biggest-group play
#: until a big clear banks a hammer, then one lone tile is broken with it.
#: The refusal at zero hammers is measured first, on the same board.
HAMMER_PROBE = """
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
function walkTo(x, y){
  let guard = 0;
  while (puzzleFacts().cur.x !== x && guard++ < 40) key(puzzleFacts().cur.x < x ? 'ArrowRight' : 'ArrowLeft');
  while (puzzleFacts().cur.y !== y && guard++ < 80) key(puzzleFacts().cur.y < y ? 'ArrowDown' : 'ArrowUp');
}
key(' ');
run(40);
/* At zero hammers a lone tile refuses to break: same press, nothing owed. */
let refusal = null;
{ const f = puzzleFacts();
  if (f.lone.x >= 0 && f.hammers === 0) {
    walkTo(f.lone.x, f.lone.y);
    const before = puzzleFacts().tiles;
    key(' '); run(2);
    refusal = { tilesBefore: before, tilesAfter: puzzleFacts().tiles,
      hammers: puzzleFacts().hammers };
  } }
/* Greedy biggest-group play until a big clear banks a hammer. */
let earn = null, guard = 0;
while (puzzleFacts().state === 'play' && puzzleFacts().hammers === 0 && guard++ < 200) {
  const f = puzzleFacts();
  if (f.best.n < 2) break;
  walkTo(f.best.x, f.best.y);
  const size = f.best.n, purse = f.hammers;
  key(' '); run(2);
  if (puzzleFacts().hammers > purse) {
    earn = { size: size, hammers: puzzleFacts().hammers };
  }
}
/* Spend: break one lone tile - exactly one tile leaves, one hammer goes,
   and the vanity score does not move. Keep playing until a lone exists. */
let spend = null; guard = 0;
while (spend === null && puzzleFacts().state === 'play' && guard++ < 200) {
  const f = puzzleFacts();
  if (f.hammers > 0 && f.lone.x >= 0) {
    walkTo(f.lone.x, f.lone.y);
    const before = puzzleFacts();
    key(' '); run(2);
    const after = puzzleFacts();
    spend = { tilesBefore: before.tiles, tilesAfter: after.tiles,
      hammersBefore: before.hammers, hammersAfter: after.hammers,
      scoreBefore: before.score, scoreAfter: after.score };
  } else if (f.best.n >= 2) { walkTo(f.best.x, f.best.y); key(' '); run(2) }
  else break;
}
console.log(JSON.stringify({ refusal: refusal, earn: earn, spend: spend,
  state: puzzleFacts().state, hammers: puzzleFacts().hammers }));
"""


#: Greedy play, wired for the loss-recap probe (C-1427). A board does not
#: jam on its own - nothing falls, nothing spawns, and a page left alone
#: sits at its opening position forever - so the losing go has to be
#: driven, the way the adventure's is. Always the biggest group, which is
#: also why it never presses a lone tile: the hammers stay in the purse,
#: and the jam that results is the one a player who saved them would meet.
RECAP_SETUP = """
function pzWalk(x, y){ let g = 0;
  while (puzzleFacts().cur.x !== x && g++ < 40) {
    press(puzzleFacts().cur.x < x ? 'ArrowRight' : 'ArrowLeft') }
  while (puzzleFacts().cur.y !== y && g++ < 80) {
    press(puzzleFacts().cur.y < y ? 'ArrowDown' : 'ArrowUp') } }
function pzStep(){ if (state !== 'play') return;
  const f = puzzleFacts();
  if (f.best.n >= 2) { pzWalk(f.best.x, f.best.y); press(' '); return }
  /* No group left. Since C-1428 the hammer is a move, so the go is not
     over yet - spend the purse on a lone tile, which is what a player
     holding one would do, and let the collapse decide whether the board
     opens up again. */
  if (PZ_SPEND && f.hammers > 0 && f.lone.x >= 0) {
    pzWalk(f.lone.x, f.lone.y); press(' ') } }
"""

#: One move, every third frame so the board is given time to fall.
RECAP_STEP = "try{ if (f % 3 === 0) { pzStep() } }catch(e){}"


def recap_route(*, spend: bool = True) -> tuple[str, str]:
    """The greedy drive, as ``recap.probe_source`` wants it.

    ``spend=False`` is the hoarder: it clears groups but never touches a
    lone tile, so the purse it banks is never used. Since C-1428 that drive
    does not end the go at all - which is the whole point of the fix, and
    the only way to see it is to compare the two.
    """

    return ("const PZ_SPEND = %s;\n" % ("true" if spend else "false")) + RECAP_SETUP, RECAP_STEP


#: What the jam line has to survive, asked of the board that just jammed.
#: Appended after ``recap.probe_source``'s own report, so the judge reads
#: two JSON lines.
#:
#: The board is **recounted straight from the grid** rather than trusted to
#: the snapshot, and the definition of a jam is checked rather than assumed:
#: every tile still standing has to be a group of one. Then the comparison
#: is interrogated the only way it can be - no drive reaches a jam with a
#: purse bigger than the board - by moving the purse and re-reading.
_RECAP_TAIL = """
/* The win case above left the board flagged as cleared. Put it back: this
   line only speaks about a jam. */
state = 'over'; cleared = false;
const pzSaid = recapLine();
let pzRecount = 0, pzSingles = 0; const pzHues = {};
for (let y = 0; y < ROWS; y++) { for (let x = 0; x < COLS; x++) {
  if (grid[y][x] < 0) continue;
  pzRecount++; pzHues[grid[y][x]] = 1;
  if (group(x, y).length === 1) pzSingles++ } }
const pzKeepT = JAM_TILES, pzKeepB = JAM_BROKEN;
/* More tiles opened than left standing: the other clause becomes the
   larger one, and its count has to follow the counter that moved. */
JAM_BROKEN = JAM_TILES + 5;
const pzSaidPurse = recapLine();
JAM_TILES = 0; JAM_BROKEN = 0;
const pzSaidNothing = recapLine();
JAM_TILES = pzKeepT; JAM_BROKEN = pzKeepB;
console.log(JSON.stringify({
  said: pzSaid, saidPurse: pzSaidPurse, saidNothing: pzSaidNothing,
  recount: pzRecount, singles: pzSingles, colours: Object.keys(pzHues).length,
  /* The purse as the game still holds it. Nothing can spend a hammer once
     the board is over, so this is what it was at the jam - and it is the
     only independent check on the snapshot's own copy of it. Without it a
     purse that is never recorded agrees with a line derived from it. */
  livePurse: hammers,
  /* The biggest group still on the board, read after the win block - which
     only ever touched state and cleared, never the grid. Under 2 means
     there is no pop available, which is exactly the condition that used to
     end the go on its own (C-1428). */
  bestN: puzzleFacts().best.n,
  tiles: JAM_TILES, hammers: JAM_HAMMERS, jamColours: JAM_COLOURS,
  broken: JAM_BROKEN,
}));
"""


def recap_probe_source(script: str, *, frames: int = 4200, spend: bool = True) -> str:
    """The loss-recap probe, driven greedily to a jam and then questioned."""

    from sidra_ai.creation.recap import probe_source

    return (
        probe_source(script, template="puzzle", frames=frames, route=recap_route(spend=spend))
        + _RECAP_TAIL
    )


def hammer_probe(script: str) -> str:
    """The page's own script, wrapped so the economy can be played out."""

    return HAMMER_PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The round's sky, judged by playing the round out (§7, C-1327): a pop
#: landed under the first sky, the clock carried into each later third, a
#: pop landed under the last sky, and the sixty-second break untouched.
#: Two pops leave the board far from a deadlock, so the round has to end
#: on the clock - which is exactly the claim.
SKY_PROBE = """
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
function walkTo(x, y){
  let guard = 0;
  while (puzzleFacts().cur.x !== x && guard++ < 40) key(puzzleFacts().cur.x < x ? 'ArrowRight' : 'ArrowLeft');
  while (puzzleFacts().cur.y !== y && guard++ < 80) key(puzzleFacts().cur.y < y ? 'ArrowDown' : 'ArrowUp');
}
/* Walks the cursor onto the biggest group and pops it. Arrow keys spend no
   frames, so the sky the pop lands under is the sky that was read. */
function popBest(){
  const f = puzzleFacts();
  if (f.best.n < 2) return 0;
  walkTo(f.best.x, f.best.y);
  const before = puzzleFacts().score;
  key(' '); run(2);
  return puzzleFacts().score > before ? 1 : 0;
}
/* The first press passes the briefing; played time starts here. */
key(' ');
run(40);
const early = puzzleFacts();
const popEarly = popBest();
/* Let the round age into each later third. 24s and 45s sit well inside
   acts 1 and 2 of the 60s round, clear of the 20s/40s boundaries. */
let guard = 0;
while (puzzleFacts().ms < 24000 && guard++ < 4000) run(1);
const mid = puzzleFacts();
while (puzzleFacts().ms < 45000 && guard++ < 8000) run(1);
const late = puzzleFacts();
const popLate = popBest();
/* The sky must not have touched the break: the clock still ends the go -
   two pops cannot deadlock the board, so 'time' is the only honest end. */
while (!roundFacts().done && puzzleFacts().state === 'play' && guard++ < 12000) run(1);
const end = roundFacts();
console.log(JSON.stringify({
  sceneEarly: early.scene, sceneMid: mid.scene, sceneLate: late.scene,
  msEarly: early.ms, msMid: mid.ms, msLate: late.ms,
  popEarly: popEarly, popLate: popLate,
  score: puzzleFacts().score, state: puzzleFacts().state,
  done: end.done, reason: end.reason,
  scenes: sceneFacts().scenes,
  hud: hudFacts(),
}));
"""


def sky_probe(script: str) -> str:
    """The page's own script, wrapped so the round's sky can be watched."""

    return SKY_PROBE.replace("SCRIPT_PLACEHOLDER", script)


def probe_source(script: str, *, reduced: bool = False) -> str:
    """The page's own script, wrapped so one pop can be watched in node."""

    return PROBE.replace("REDUCED_INPUT", "true" if reduced else "false").replace(
        "SCRIPT_PLACEHOLDER", script
    )

__all__ = [
    "PUZZLE_DIFFICULTY",
    "PUZZLE_HOW",
    "PUZZLE_SCRIPT",
    "PUZZLE_TITLE",
    "PUZZLE_WORDS",
    "PROBE",
    "probe_source",
    "HAMMER_PROBE",
    "hammer_probe",
    "SKY_PROBE",
    "sky_probe",
]
