"""Seeded background music for every generated game. No files, no fetches.

The SFX half of §1's "効果音と音楽" landed with C-1017; this is the music
half, built to the three facts recorded in
``docs/research/game-design-notes.md`` §10:

* **Two clocks** (web.dev "A Tale of Two Clocks"): a low-precision JS loop
  reserves notes only inside a 0.1s lookahead window, and the actual sound
  starts on the AudioContext's own high-precision clock. Here the JS clock
  is the requestAnimationFrame timestamp, which every generated page
  already drives - so the scheduler needs no timer of its own and a probe
  can turn the clock by hand.
* **Retro loops are short** (abagames, procedural sound): four bars,
  repeated, as two tracks - a melody and a bass sitting roughly 1:4 under
  it so the low end never muddies.
* **Major pentatonic cannot really go wrong** (no semitones, no tritone):
  a random walk over scale tones 1,2,3,5,6 makes no harmonic mistakes, so
  a seeded walk is safe to ship unheard.

The tune is woven from the request's seed with its own generator - the
game's ``rand()`` deals the world and is not consumed - so the same words
are the same game *and* the same song, and adding music changed no
template's layout.

House rules carried over from the SFX preamble, which this one sits right
after: nothing plays before the player's first real input (the browsers'
autoplay rule, and C-1111's), ``M`` mutes the music the same as the
effects, and while a fight is on the volume takes the §6 観察 4 step -
under the mute, and under ``MAX_GAIN``.
"""

from __future__ import annotations

#: Names this preamble introduces, held to by the vocabulary test.
PREAMBLE_NAMES: tuple[str, ...] = (
    "musicTick",
    "musicFacts",
    "musicArm",
    "MUSIC_ON",
    "MUSIC_N",
)

MUSIC_PREAMBLE = """
/* --- BGM: four pentatonic bars, woven from the request's seed (§10) ----
   The rAF timestamp is the JS-side clock; notes are reserved 0.1s ahead
   and start on the audio clock. Melody and bass only - short, repeated,
   and impossible to make dissonant on this scale. */
const MUSIC_STEP=0.27,MUSIC_STEPS=32,MUSIC_AHEAD=0.1;
let MUSIC_ON=false,MUSIC_NEXT=-1,MUSIC_I=0,MUSIC_N=0;
/* Its own generator: the game's rand() deals the world, this one only
   deals the tune, so the same request stays the same game AND the same
   song, and neither draw disturbs the other. MUSIC_SEED_INPUT is its
   own token, not SEED: the template's const sits in the temporal dead
   zone this early in the script, and the daily switch must not change
   the song under a running player. */
let MUSIC_RS=((MUSIC_SEED_INPUT>>>0)+11)||1;
function musicRand(){MUSIC_RS=(MUSIC_RS*48271)%2147483647;return MUSIC_RS/2147483647}
/* Major pentatonic over two octaves on an A3 root: scale tones 1,2,3,5,6
   carry no semitone and no tritone, so the walk below cannot land on a
   harmonic mistake (§10 事実 3). */
const MUSIC_SCALE=[0,2,4,7,9,12,14,16,19,21];
function musicHz(d){return 220*Math.pow(2,MUSIC_SCALE[d]/12)}
const MUSIC_MEL=[],MUSIC_BASS=[];
(function(){let d=4;
  for(let i=0;i<MUSIC_STEPS;i++){
    if(musicRand()<0.25){MUSIC_MEL.push(-1)}
    else{d=Math.max(0,Math.min(9,d+Math.floor(musicRand()*5)-2));
      MUSIC_MEL.push(d)}
    /* The bass walks on the beat, root or fifth, two octaves down - the
       "about 1:4" separation that keeps the low end clean (§10 事実 2). */
    MUSIC_BASS.push(i%4===0?(musicRand()<0.7?0:3):-1)}})();
/* Armed by the first real input, the same moment the SFX unlock: nothing
   hums over the briefing before the player has touched anything. */
function musicArm(){MUSIC_ON=true}
addEventListener('keydown',musicArm);
addEventListener('pointerdown',musicArm);
function musicNote(freq,off,dur,vol,wave){MUSIC_N++;
  try{
    if(!AC){AC=new (window.AudioContext||window.webkitAudioContext)()}
    if(AC.state==='suspended'){AC.resume()}
    const t0=AC.currentTime+Math.max(0,off);
    const osc=AC.createOscillator(),gain=AC.createGain();
    osc.type=wave;osc.frequency.setValueAtTime(freq,t0);
    /* The fight raises the music one step too (§6 観察 4), below the same
       ceiling and the same mute as everything else. */
    const v=Math.min(MAX_GAIN,vol*(COMBAT?COMBAT_GAIN:1));
    gain.gain.setValueAtTime(v,t0);
    gain.gain.exponentialRampToValueAtTime(0.001,t0+dur);
    osc.connect(gain);gain.connect(AC.destination);
    osc.start(t0);osc.stop(t0+dur+0.02);
  }catch(err){/* no audio device is a machine, not a bug */}}
function musicTick(tms){
  if(!MUSIC_ON||MUTED)return;
  const now=tms/1000;
  /* First tick, and any long suspension, restart the reservation clock:
     catching up a paused tab in one burst would be a chord of the whole
     backlog, not a resume. */
  if(MUSIC_NEXT<0||now-MUSIC_NEXT>1){MUSIC_NEXT=now}
  /* The fight doubles the pulse (§6 定量: combat shots run at half the
     length of talk - 2.1s vs 4.4s - so combat keeps time twice as fast).
     Same four bars, same notes, twice the tread; the gain step §6 観察 4
     already gives every note stays as it was, and M still wins. */
  const stepNow=COMBAT?MUSIC_STEP*0.5:MUSIC_STEP;
  while(MUSIC_NEXT<now+MUSIC_AHEAD){
    const i=MUSIC_I%MUSIC_STEPS,off=MUSIC_NEXT-now;
    const m=MUSIC_MEL[i];
    if(m>=0)musicNote(musicHz(m),off,stepNow*0.9,0.045,'square');
    const b=MUSIC_BASS[i];
    if(b>=0)musicNote(musicHz(b)/4,off,stepNow*1.8,0.055,'triangle');
    MUSIC_I++;MUSIC_NEXT+=stepNow}}
/* The page's own frame loop is the JS-side clock. Later wrappers (pad,
   round) capture this one, so the tick survives the round banner too. */
const MUSIC_RAF=requestAnimationFrame;
requestAnimationFrame=function(fn){
  return MUSIC_RAF(function(t){musicTick(t);fn(t)})};
function musicFacts(){return {on:MUSIC_ON,muted:MUTED,scheduled:MUSIC_N,
  step:MUSIC_STEP,steps:MUSIC_STEPS,
  mel:MUSIC_MEL.slice(),bass:MUSIC_BASS.slice()}}
"""

#: The page driven in node, the same no-op browser the template probes
#: build: silence before the first input, notes reserved once it lands,
#: and the reservation stops the moment ``M`` mutes.
PROBE = """
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
/* Quiet before anyone touches anything. */
run(60);
const before = musicFacts();
/* The first input arms the music (and passes the briefing). */
key(' ');
run(300);
const playing = musicFacts();
/* The fight doubles the pulse: the same 300 frames must reserve about
   twice the notes while combat is on (§6 定量, C-1312). */
const calmN = musicFacts().scheduled - before.scheduled;
combat(true);
run(300);
const fightN = musicFacts().scheduled - playing.scheduled;
combat(false);
/* M mutes: no further notes are reserved - in or out of combat. */
key('m');
combat(true);
const atMute = musicFacts().scheduled;
run(200);
combat(false);
const after = musicFacts();
console.log(JSON.stringify({
  beforeOn: before.on, beforeN: before.scheduled,
  playingN: playing.scheduled, calmN: calmN, fightN: fightN,
  atMuteN: atMute, afterN: after.scheduled,
  mel: playing.mel, bass: playing.bass, steps: playing.steps,
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so the tune can be watched in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = ["MUSIC_PREAMBLE", "PREAMBLE_NAMES", "PROBE", "probe_source"]
