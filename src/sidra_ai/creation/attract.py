"""The title runs the game behind its own curtain (§17).

An attract mode is the arcade's answer to "what is this?": the cabinet
plays itself while nobody is at it, because a moving game says in a second
what three lines of text say in ten. SIDRA's title gate held the loop shut
- the template never got a frame - so a first visit was a still picture and
a paragraph.

The material was already there. C-1404's instrument proved that a racing
page drives itself to the finish with nobody touching it, which is exactly
what a demo needs: a template that produces a moving picture from no input.

Three rules, and they are the whole design:

* **The demo earns nothing.** It is not a round somebody played, so it
  banks no score, sets no best, leaves no ghost and counts no defeat. This
  is not a new rule - ``roundBank`` already refuses an untouched round
  (C-1123), and the gate is what marks a round as touched, so the demo is
  covered by the rule that already exists rather than by an exception.
* **Pressing start begins at the beginning.** The demo has moved the world,
  so it is rewound before play: the template's own ``reset`` and the round
  clock, both. Joining a demo half way through would hand somebody a
  forty-second round and a car already round the first bend.
* **It is behind a curtain, not instead of one.** The title still says what
  the game is and how to start it; the demo runs dimmed underneath.
"""

from __future__ import annotations

from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: Wired here first, as the item allows. Racing is the template C-1404
#: measured driving itself to the finish line, so it is the one that
#: certainly produces a moving picture from no input at all. Shooter
#: (C-1338) is the second: it needs one held input, which is what a pilot
#: line is for. Marble (C-1349) is the fourth: it rolls itself, and the
#: pilot is the steering hand its unwired reason asked for. Platformer
#: (C-1433) is the fifth: its unwired reason described a page with no
#: input, and a walking hand is exactly what the pilot mechanism is.
#: Duel (C-1434) is the sixth, unblocked by C-1435: its fights hitstop on
#: every landed blow, and until the motion bar stopped counting frames
#: the page held still itself, an honest duel demo could not pass it.
#: Adventure (C-1439) is the seventh: the hero does not walk unbidden, and
#: the walk is the whole demo - out of the waking room, cutting what is in
#: the way.
#: Catch (C-1438) is the eighth, and the first CLOCK-BOUND one: it has
#: no ending of its own (ROUND_LIVE is empty), so its demo loops on a
#: fixed slice instead - the arcade's own habit of showing fifteen
#: seconds and starting over. See ATTRACT_SLICE.
#: Fishing (C-1356) is the ninth, the second clock-bound one, and the
#: purest case for the live receipt: its marker sweeps for ever, so an
#: unpiloted page passes the motion bar on its own - only the receipt
#: can tell the game from the screensaver its unwired reason described.
#: Puzzle (C-1440) is the tenth and last, and the stillest page of them
#: all: a board nobody clicks paints the identical picture for ever, so
#: the hand is the only thing that moves it. It waited on C-1441, which
#: stopped the veil check being decided by whether the last frame of the
#: run happened to land inside a hitstop.
ATTRACT_TEMPLATES: tuple[str, ...] = (
    "racing", "shooter", "kaiju", "marble", "platformer", "duel",
    "adventure", "catch", "fishing", "puzzle")

#: Why each of the others is not wired yet, in the same shape as
#: ``COMBO_UNWIRED``: "not yet" and "not applicable" are different answers
#: and only the first is a backlog item. Every reason here is about what
#: the template *does* with no input, which is the only thing that decides
#: whether a demo of it is worth watching.
#:
#: Empty since C-1356 and C-1440 landed together: every template plays
#: itself behind its title now. Kept rather than deleted because the
#: table is what the next new template is measured against - a template
#: with no demo has to say why, here, in one line.
ATTRACT_UNWIRED: dict[str, str] = {}

#: What to call to put the world back to its first frame. Every template
#: that has one calls it ``reset``; the expression is written down rather
#: than assumed so a template that renamed it fails the judge instead of
#: quietly starting people mid-demo.
ATTRACT_RESET: dict[str, str] = {
    "racing": "reset()", "shooter": "reset()", "kaiju": "reset()",
    "marble": "reset()",
    # The pilot's held key is released HERE because platformer's own
    # reset() does not touch ``keys`` - unlike the shooter, whose reset
    # lets go of ``fire`` itself. Without this the player's first go
    # would start with the demo's hand still on the arrow.
    "platformer": "keys.ArrowRight=false;reset()",
    # Duel's reset rebuilds both fighters, so the pilot's held charge
    # goes with them.
    "duel": "reset()",
    # Adventure's reset() rebuilds the hero but leaves ``keys`` alone, so
    # the demo's walk has to be let go of here (platformer's case, and
    # for the same reason): otherwise the player's first go begins with
    # the hero already striding right.
    "adventure": "keys.arrowright=keys.arrowup=keys.arrowdown=false;reset()",
    # Puzzle's pilot writes ``cur`` and calls pop() rather than holding a
    # key, so there is no hand to open - reset() rebuilds the board and
    # the cursor with it.
    "puzzle": "reset()",
    # Catch has no reset() of its own - the round clock is its only
    # ending - so the rewind rebuilds the world by hand. The reseed is
    # load-bearing: the demo consumed the random stream, and a player
    # handed a board the control page would not have drawn fails the
    # handover comparison ten seconds in.
    "catch": "items=[];score=0;caught=0;missed=0;t=0;firstDrop=true;"
    "px=0.5;shown=0.5;BSQ=1;rs=(SEED>>>0)||1",
    # Fishing has no reset() either, but the OPPOSITE reseed rule to
    # catch: its one rand() draw happens at load (SPOT) and play never
    # touches the stream, so the control page's rs is the post-SPOT
    # state - reseeding here would be the divergence, not the cure.
    "fishing": "score=0;hits=0;crits=0;casts=0;flash=0;pos=0;dir=1;"
    "msg='SPACE / クリックで合わせる'"}


#: Demo slice length, in gate frames, for templates with no ending of
#: their own (ROUND_LIVE empty: the round clock is their only break, and
#: the clock does not run behind the title). The gate rewinds the demo
#: every this-many frames and counts it a loop - fifteen seconds, the
#: arcade's own attract-slice habit. Zero means "the template ends
#: itself" and the gate keeps listening to roundEnded() alone.
ATTRACT_SLICE: dict[str, int] = {"catch": 900, "fishing": 900}


def slice_frames(template: str) -> int:
    """How long this template's demo slice runs, or 0 for its own end."""

    return ATTRACT_SLICE.get(template, 0)

#: One line of piloting, run every demo frame before the template's step
#: (C-1338). The arcade's attract mode is a recorded hand on the real
#: controls, and this is its smallest form: the shooter's hand holds the
#: trigger, and nothing else. The line drives the template's OWN input
#: state, so the handover needs no undoing beyond the template's reset -
#: shooter's reset() already lets go of ``fire``. Racing needs no hand at
#: all, which is why it has no entry. The second clause is the receipt:
#: ATTRACT_LIVE goes up the moment the game's core verb lands on screen
#: (a kill, here), which is what the judge reads to tell a demo with a
#: game in it from a moving screensaver.
ATTRACT_PILOT: dict[str, str] = {
    "shooter": "fire=true;if(kills>0)ATTRACT_LIVE=1",
    # Kaiju (C-1344): pace under the leg and keep shooting - the whole
    # game in one held stance, at a rate that leaves the picture moving
    # between hitstops. The receipt is a weak-point cycle landed.
    # NOTE the counter: a pilot line runs inside the gate's tick, whose
    # own parameter is named ``t`` - it SHADOWS a template's global ``t``
    # with the rAF timestamp (a float, so ``t%16===0`` almost never
    # fired). ATTRACT_FRAMES is the gate's own frame count and nothing
    # shadows it; pilots must not lean on template globals the tick hides.
    "kaiju": "me.x=legX()+18*Math.sin(ATTRACT_FRAMES/25);"
    "if(ATTRACT_FRAMES%16===0)fire();if(cycles>0)ATTRACT_LIVE=1",
    # Marble (C-1349): the steering demo its unwired reason asked for. The
    # rule is COMBO_PROBE's, condensed: a block close ahead and close
    # beside is dodged toward the centre line, otherwise the marble aims
    # at the next gate - nudged at most 3.4/frame, the same speed
    # partsSteerX gives a held arrow key (kaiju's pilot writing me.x is
    # the precedent for the direct hand). The receipt is a HOT gate taken,
    # not any gate: the opening gift gate lines itself up, so an unpiloted
    # marble crash-looping off the first block still "passes a gate" - and
    # still clears the motion bar (measured: 43 crash loops, 3941 moving
    # frames). A hot gate stands in a block's shadow; taking one IS the
    # swerve, so it is the one verb only a steered demo can land.
    # ATTRACT_FRAMES is not needed here, but the C-1344 rule still binds:
    # the tick's ``t`` shadows marble's own ``t``.
    "marble": "let MB=null,MG=null;"
    "things.forEach(o=>{const dz=o.z-ball.z;if(o.done||dz<=0)return;"
    "if(o.kind==='block'&&dz<150&&!MB)MB=o;"
    "if(o.kind==='gate'&&dz<900&&!MG)MG=o});"
    "const MA=MB&&Math.abs(MB.x-ball.x)<46?MB.x+(MB.x<0?90:-90):MG?MG.x:null;"
    "if(MA!==null)ball.x+=Math.max(-3.4,Math.min(3.4,MA-ball.x));"
    "if(hotTaken>0)ATTRACT_LIVE=1",
    # Platformer (C-1433): walk right on the template's own key state and
    # hop at a ledge's edge - jump when grounded with no floor within a
    # step ahead at this height or below (a higher next ledge also reads
    # as "no floor ahead", which is exactly when climbing needs a jump).
    # The receipt is the goal stretch reached: a page with no pilot
    # stands at x=60 for ever, so only a real walk lights it.
    "platformer": "keys.ArrowRight=true;"
    "if(me.ground&&!plats.some(p=>me.x+30>p.x-6&&me.x+30<p.x+p.w+6"
    "&&p.y>=me.y-1&&p.y<me.y+60))tryJump();"
    "if(me.x>LW*0.72)ATTRACT_LIVE=1",
    # Duel (C-1434, loop A's design): the CPU side fights on its own, so
    # the hand only plays the player - step out of the telegraphed lane
    # (e.aim holds it for AIM_LOCK frames), charge, step into the
    # enemy's lane and release. The receipt is a landed blow: an
    # unpiloted duel is the CPU executing a statue, and its own KO loops
    # pass everything but this.
    # Adventure (C-1439): walk right along the row the hero wakes on -
    # which is the row the door out is on - and cut what can be cut.
    # Measured on the real forest rather than assumed: row 4 reads
    # 1 0 [hero] 2 0 2 0 2 0 3 3 3 0 ... 5, so the walk meets grass it
    # can clear and then a POND it cannot. Grass is solid until cut and
    # ponds are solid for ever, so "hold right and swing" wedges against
    # the water. Hence the step aside.
    #
    # It reads TWO corners rather than one tile ahead, because that is
    # what the template's own movement reads, and a pilot that tests
    # less than the game does gets stuck where the game says it may not
    # pass. The first version tested one tile and wedged 20px from the
    # start for all 4200 frames: the hero wakes at y=144, the top EDGE
    # of its row, so its 10px box straddles two rows and the NPC sitting
    # in the row above (tile 8, solid) was blocking a walk that looked
    # clear on the hero's own row. Stepping off the boundary is what
    # frees it, and the step is self-cancelling - once the box is inside
    # one row the corner stops reading solid.
    #
    # It also holds the row it woke on when nothing is in the way, and
    # that is not tidiness: build() puts every door of every room on row
    # 4 (forest[4][GW-1], cave[4][0], cave[4][GW-1], altar[4][0]), so
    # that row IS the way through. Without the bias the sidesteps only
    # ever accumulated one way - measured, the hero ended its 70 seconds
    # in row 7 against the right wall, having walked and cut the whole
    # time but never found the door.
    #
    # ``hero.dir`` is set before the swing because holding up or down
    # turns the hero that way on the step, and a swing goes where the
    # hero faces - a demo that steps around a pond and then cuts the
    # air is one the receipt would rightly refuse.
    #
    # The receipt is a gem, and gems come only from cutting grass.
    # Unlike marble and duel, an unpiloted adventure fails on its own
    # merits and not only on the receipt - measured with the pilot
    # removed: the picture changes on 17.0% of frames and the round
    # never ends (0 loops), because the roamers are the only things
    # moving and they do not come for a hero standing in its bed. That
    # is ATTRACT_UNWIRED's old line, confirmed rather than assumed.
    "adventure": "const AX=hero.x+13,ALY=OY+4*TILE+TILE/2,"
    "AU=tileAt(AX,hero.y-10),AD=tileAt(AX,hero.y+10),"
    "ABU=solid(AX,hero.y-10)&&AU!==2,ABD=solid(AX,hero.y+10)&&AD!==2;"
    "if(AU===2||AD===2){hero.dir=1;swing()}"
    "keys.arrowright=true;"
    "keys.arrowdown=(ABU&&!solid(hero.x,hero.y+34))"
    "||(!ABU&&!ABD&&hero.y<ALY-3);"
    "keys.arrowup=!keys.arrowdown&&((ABD&&!solid(hero.x,hero.y-34))"
    "||(!ABU&&!ABD&&hero.y>ALY+3));"
    "if(hero.gems>0)ATTRACT_LIVE=1",
    # Puzzle (C-1440): one move every twelve frames, about five a second.
    # The board's own puzzleFacts() already reads what the hand needs -
    # ``best`` and ``lone`` are C-1322's economy read - so the pilot is
    # only the choosing: clear the biggest group, and when none is left
    # break a lone tile.
    #
    # The hammer is not a flourish. Measured without it the demo stalls
    # the moment only lone tiles remain (6.8% of frames repaint, and it
    # never ends), which is C-1428's "a hammer IS a move" seen from the
    # demo's side.
    #
    # The pace was chosen for the picture, not for the bar. Motion sits
    # on a wide plateau - a move every 6, 10, 12, 16 or 24 frames all
    # repaint 99.5-99.9% of advanced frames - and only the frantic end
    # falls off it (every 3 frames: 90.6%; every frame: the board
    # thrashes through 150 rounds and hitstop swallows most of them).
    # Twelve is the middle of the plateau and reads as somebody playing.
    #
    # puzzleFacts() also offers ``target``, C-1427's "group with a
    # foreign tile above it", i.e. a pop guaranteed to drop something.
    # Preferring it looks like the more thoughtful demo and was measured
    # to make no difference at all (99.7% either way, 12 loops against
    # 13), so it is not here: at five moves a second the board is never
    # at rest long enough for one non-dropping pop to show. Written down
    # because it is the obvious thing to add back.
    "puzzle": "if(state==='play'&&ATTRACT_FRAMES%12===0){const PF=puzzleFacts();"
    "const PT=PF.best.n>1?PF.best:(PF.hammers>0?PF.lone:null);"
    "if(PT&&PT.x>=0){cur={x:PT.x,y:PT.y};pop()}}"
    "if(score>0)ATTRACT_LIVE=1",
    "duel": "if(p.stun<=0){"
    "if(e.hold&&e.aim===p.lane)p.lane=e.aim===2?1:e.aim+1;"
    "if(!p.hold&&p.beam<=0)p.hold=true;"
    "if(p.hold&&p.charge>26&&!(e.hold&&e.aim===p.lane)){"
    "if(e.lane!==p.lane)p.lane=e.lane;fire(p)}}"
    "if(e.hp<3)ATTRACT_LIVE=1",
    # Catch (C-1438): chase the lowest item - the same "move at the
    # nearest" hand C-1424 drives with - by writing the pointer target
    # the template itself eases toward. The receipt is a WORKED-FOR
    # count: the opening gift and the items that happen to fall into the
    # band catch themselves, and a still bowl was measured collecting
    # 6-12 per slice by luck alone while the chasing hand collects 37 -
    # so the receipt sits at 20, a total no still bowl reaches.
    "catch": "let CB=null;items.forEach(i=>{if(!CB||i.y>CB.y)CB=i});"
    "if(CB)px=Math.max(0,Math.min(1,CB.x));"
    "if(caught>=20)ATTRACT_LIVE=1",
    # Fishing (C-1356): cast as the marker crosses dead centre, so every
    # cast is a 会心 - the game's own best picture. The cooldown against
    # the gate's own counters is load-bearing: the cast's hitstop freezes
    # ``pos`` INSIDE the window, and a pilot without it re-casts the
    # frame the stop lifts, locking the page into hitstop for ever
    # (measured: 4081 of 4199 frames self-held - the demo as a statue
    # of its own best moment). The receipt is a fish landed: the sweep
    # alone never casts, so a still hand can never light it.
    "fishing": "if(Math.abs(pos-SPOT)<SPEED*0.55"
    "&&(ATTRACT_FRAMES-ATTRACT_MARK)>casts*80)cast();"
    "if(hits>0)ATTRACT_LIVE=1",
}


def wired(template: str) -> bool:
    """Whether this template plays itself behind the title."""

    return template in ATTRACT_TEMPLATES and template in ATTRACT_RESET


def reset_call(template: str) -> str:
    """The template's own way back to frame one, or a no-op."""

    return ATTRACT_RESET.get(template, "")


def pilot_call(template: str) -> str:
    """The demo's hand on the template's own controls, or a no-op."""

    return ATTRACT_PILOT.get(template, "")




#: Runs a generated page in node: leave it alone on its title for a while,
#: then press start. The whole claim is about what happens *behind* a shut
#: gate, so the canvas is a recorder rather than a swallowing Proxy - "the
#: picture moves" is a claim about paint, and only paint can settle it.
PROBE = KEY_EVENT_JS + """
const attractNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : attractNothing),
  apply: () => attractNothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false });
let attractClock = 0;
globalThis.performance = { now: () => attractClock };
const attractKeys = [], attractPointers = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') attractKeys.push(fn) };
globalThis.Image = function(){ return attractNothing };
const attractStore = {};
globalThis.localStorage = {
  getItem: (k) => (k in attractStore ? attractStore[k] : null),
  setItem: (k, v) => { attractStore[k] = String(v) },
  removeItem: (k) => { delete attractStore[k] } };
globalThis.location = { reload: () => {} };
/* Every fill, with the colour it was made in: the demo has to move, and
   the veil over it has to be a veil rather than a lid. */
let attractOps = [], attractInk = null;
globalThis.document = { readyState: 'complete',
  createElement: () => attractNothing, querySelector: () => null,
  getElementById: () => ({
    width: 720, height: 320, style: {},
    addEventListener: (type, fn) => {
      if (type === 'pointerdown') attractPointers.push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => new Proxy({
      fillText: (t, x, y) => { attractOps.push('t:' + attractInk + ':' + String(t)
        + ':' + Math.round(Number(x) || 0) + ':' + Math.round(Number(y) || 0)) },
      fillRect: (x, y, w, h) => { attractOps.push('r:' + attractInk + ':'
        + [x, y, w, h].map(v => Math.round(Number(v) || 0)).join(',')) } }, {
      get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : attractNothing)),
      set: (t, k, v) => { if (k === 'fillStyle') { attractInk = String(v) } return true } }) }) };
/* A queue, not a single slot. A gate that armed the loop *and* let the
   demo arm it would schedule two callbacks for the next frame, then four,
   then eight - and a one-slot stub would quietly drop all but the last and
   show a page that looked perfectly healthy. The browser keeps every one
   of them, so this keeps every one of them. */
let attractQueue = [];
/* The paint of the last frame the game was actually drawn on. Kept once
   rather than per frame for the same reason idlePaint always was. */
let attractLastDrawn = null;
globalThis.requestAnimationFrame = (fn) => { attractQueue.push(fn); return attractQueue.length };
SCRIPT_PLACEHOLDER
/* One number for a frame's worth of paint. A demo that is running draws a
   different picture every frame; a title with nothing behind it draws the
   same one for ever. */
/* Did the page draw the GAME this frame, or only the title over it?
   Structural, so it needs no threshold on how many ops count as a game:
   the template fills the whole canvas with its own ground and the gate
   fills it again with its panel, so a frame with the game in it carries
   more than one full-canvas fill and a frame the page skipped carries
   only the gate's. Measured on puzzle, duel and adventure: exactly 1 on
   every title-only frame, 2 or more on every frame with the game in it.

   It has to be asked per frame because a page that hitstops does not
   draw on the frames it holds (C-1435), so "the last frame" is a frame
   the demo may simply have been still for - which is a property of the
   pop's timing against the frame count, not of the demo (C-1441). */
function attractDrewGame(ops){ let n = 0;
  for (const op of ops) {
    if (op.startsWith('r:') && op.endsWith(':0,0,720,320')) { n++ } }
  return n > 1 }
function attractHash(ops){ let h = 2166136261;
  const s = ops.join('|');
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0 }
  return h }
function attractRun(frames){ const seen = [];
  for (let i = 0; i < frames && attractQueue.length; i++) {
    const due = attractQueue; attractQueue = [];
    /* A loop that is multiplying doubles every frame. Stop and report the
       count rather than running the frame: a few doublings more and the
       paint for one frame exhausts the heap, and a probe that dies is a
       probe that cannot say why. */
    if (due.length > 8) { seen.push({ hash: 0, ops: 0, calls: due.length, held: 0 }); break }
    /* Whether the PAGE ITSELF is holding this frame still (C-1435): the
       juice wrapper spends hitstop by returning without drawing, so an
       unchanged picture here is the design working, not a demo frozen.
       Read before the frame fires - firing is what spends the stop. */
    const held = (typeof HITSTOP !== 'undefined' && HITSTOP > 0) ? 1 : 0;
    attractOps = []; attractClock += 50 / 3;
    for (const fn of due) { fn(attractClock) }
    const drew = attractDrewGame(attractOps);
    if (drew) { attractLastDrawn = attractOps.slice() }
    seen.push({ hash: attractHash(attractOps), ops: attractOps.length,
      calls: due.length, held: held, drew: drew ? 1 : 0 }) }
  return seen }
/* Everything a go is made of, read off the page. Compared between a run
   that watched the demo and one that pressed at once: if the demo left
   anything behind, two snapshots taken at the same moment differ. */
function attractSnap(){
  const out = { gate: gateFacts(), attract: attractFacts(), round: roundFacts(),
    running: attractQueue.length > 0 };
  try { out.race = (typeof raceFacts === 'function') ? raceFacts() : null }
  catch (e) { out.race = null }
  try { out.ghost = (typeof ghostFacts === 'function') ? ghostFacts() : null }
  catch (e) { out.ghost = null }
  try { out.combo = (typeof comboFacts === 'function') ? comboFacts() : null }
  catch (e) { out.combo = null }
  try { out.skin = (typeof skinFacts === 'function') ? skinFacts() : null }
  catch (e) { out.skin = null }
  try { out.beats = failBeats() } catch (e) { out.beats = null }
  try { out.touched = roundTouched() } catch (e) { out.touched = null }
  out.store = JSON.parse(JSON.stringify(attractStore));
  return out }
const atLoad = attractSnap();
const idle = attractRun(IDLE_INPUT);
/* The whole of the last idle frame on which the game was drawn, kept
   once rather than per frame: the veil is a claim about one picture, and
   four thousand of them would be a megabyte of JSON to say it. It is the
   last DRAWN frame and not simply the last one because the veil can only
   be judged over a picture that has something under it - and a page that
   never drew one falls back to the plain last frame, which is what says
   so (C-1441). */
const idlePaint = attractLastDrawn || attractOps.slice();
const beforePress = attractSnap();
if (PRESS_INPUT) {
  const ev = probeKey(' ');
  attractKeys.forEach(fn => fn(ev));
}
/* Taken before a single playing frame: whatever the demo did has to be
   gone by the time the player is handed the game, not one frame later. */
const atPress = attractSnap();
const played = attractRun(PLAY_INPUT);
const afterPlay = attractSnap();
console.log(JSON.stringify({
  atLoad: atLoad, idle: idle, idlePaint: idlePaint, beforePress: beforePress,
  atPress: atPress, played: played, afterPlay: afterPlay,
}));
"""


def probe_source(script: str, *, idle: int = 240, press: bool = True, play: int = 30) -> str:
    """The page's own script, wrapped so its title screen can be watched."""

    return (
        PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("IDLE_INPUT", str(int(idle)))
        .replace("PRESS_INPUT", "true" if press else "false")
        .replace("PLAY_INPUT", str(int(play)))
    )


__all__ = [
    "ATTRACT_PILOT",
    "ATTRACT_RESET",
    "ATTRACT_SLICE",
    "ATTRACT_TEMPLATES",
    "ATTRACT_UNWIRED",
    "PROBE",
    "pilot_call",
    "probe_source",
    "reset_call",
    "slice_frames",
    "wired",
]
