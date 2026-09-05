"""Synthesised sound effects for every generated game. No files, no fetches.

The harsh review scored our games zero and the first reason was silence: a
sword with no swish, a beam with no roar. The knowledge base
(``docs/research/game-design-notes.md`` §1-2) says two things about that -
sound is the cheapest half of game feel, and the classic 8-bit palette
(sfxr's pickup / laser / explosion / hit presets) is nothing but an
oscillator, a short envelope and a frequency slide. That is buildable on the
Web Audio API in a few dozen lines, which keeps the house rule every
template lives by: one file, nothing external. The sfxr *idea* is the
reference; no code is ported.

Contract, mirroring :mod:`sidra_ai.creation.animation`:

* ``SFX_PREAMBLE`` is prepended to every template's script and defines one
  function, ``sfx(name)``, plus an ``M`` mute toggle.
* Browsers refuse audio before a user gesture, so the AudioContext is
  created lazily inside ``sfx`` - the first call happens inside a keydown or
  pointerdown handler by construction, because every ``sfx`` call sits on a
  player action or its consequence.
* A missing name is silence, not an error: a template asking for a sound
  this preamble does not know must keep playing.
* ``PREAMBLE_NAMES`` lists what templates may reference, so a test can hold
  templates and preamble to the same vocabulary.

One further rule came out of watching the owner's episode (§6 観察 4). Its
combat windows sit at -13.8..-16.5 LUFS and are audibly louder than the
talking scenes: **the film does not only play different sounds when the
fighting starts, it plays them louder.** So ``combat(true)`` raises the gain
of every effect by one step for as long as the fight is on.

Two things that step must not become. It is **not** a second mute: ``M``
still silences everything, in combat or out, because a volume feature that
can override the operator's mute is a bug wearing a design. And it is
capped, because a game whose fight scenes clip is not louder, it is broken.
"""

from __future__ import annotations

import json

#: The names templates may call. One vocabulary for all four games, so a new
#: template picks from the same drawer instead of growing private sounds.
PREAMBLE_NAMES: tuple[str, ...] = (
    "sword",
    "cut",
    "gem",
    "key",
    "hurt",
    "fire",
    "charge",
    "clash",
    "catch",
    "powerup",
    "win",
    "lose",
    "step",
)

#: How much louder an effect is while a fight is on. The episode gives a gap
#: measured in LUFS between its combat and dialogue windows but no dialogue
#: figure to subtract, so an exact dB step cannot honestly be derived from
#: it. ×2 amplitude (about +6 dB) is a deliberately conservative stand-in for
#: "audibly louder"; the number the judge checks is that the step exists,
#: survives into the page, and stays under the mute - not this constant.
COMBAT_GAIN = 2.0

#: Nothing is ever played above this, whatever the multiplier does. A fight
#: that clips is not loud, it is broken.
#:
#: C-1410 (a): today no sound reaches this ceiling - the loudest is hurt at
#: 0.24, 0.48 in combat - so ``Math.min(MAX_GAIN, ...)`` is an identity for
#: every shipped value. That is intentional headroom, not a bug: the levels
#: were picked by the §2/§6 loudness work and three sound-focused review
#: cycles (C-1304/C-1308/C-1317) never found them too quiet, while the
#: ceiling stays armed against a future louder voice or stacked sources.
#: Anyone changing gains toward the ceiling must keep the volume axis
#: (C-1408) multiplying *after* it - its judge probes that order with a
#: synthetic ceiling-reaching gain precisely because no real one exists.
MAX_GAIN = 0.9

#: Each effect is (wave, start Hz, end Hz, duration s, gain). The numbers
#: follow the sfxr preset shapes described in the knowledge base: pickups
#: rise, lasers fall fast, hurt is a low square drop, explosions are noise.
SFX_PREAMBLE = """
let AC=null,MUTED=false,COMBAT=false,NOISE_BUF=null;
const COMBAT_GAIN=COMBAT_GAIN_TOKEN,MAX_GAIN=MAX_GAIN_TOKEN;
addEventListener('keydown',e=>{if(e.key==='m'||e.key==='M'){MUTED=!MUTED}});
/* One step louder while the fight is on (§6 観察 4). Deliberately not a
   second mute: M still wins, below. */
function combat(on){COMBAT=!!on}
function combatOn(){return COMBAT}
/* The listener's own dial (C-1408), read live so the panel's value is the
   one the next sound uses. Applied *after* the ceiling on purpose: the
   fight's loudness step is a ratio between two gains, and a factor that
   went in before Math.min would be squeezed by the clamp at full volume
   and not at half - the ratio §6 measures would then depend on where the
   slider happens to sit. Multiplying afterwards leaves every ratio in the
   mix exactly as its author set it, and only the whole gets quieter.
   Guarded: the preamble sits above pages that may have no panel. */
function masterGain(){try{return Math.min(1,Math.max(0,tuneNum('volume',100)/100))}
  catch(e){return 1}}
function sfxGain(name){const spec=SFX_TABLE[name];if(!spec)return 0;
  return Math.min(MAX_GAIN,spec[4]*(COMBAT?COMBAT_GAIN:1))*masterGain()}
const SFX_TABLE={
  sword:['square',420,180,0.09,0.18],
  cut:['triangle',700,320,0.08,0.2],
  gem:['square',660,1320,0.12,0.16],
  key:['triangle',520,1040,0.18,0.2],
  hurt:['noise',1800,180,0.22,0.24],
  fire:['sawtooth',900,140,0.3,0.2],
  charge:['sawtooth',120,480,0.25,0.1],
  clash:['square',300,260,0.06,0.12],
  catch:['triangle',500,900,0.09,0.16],
  powerup:['vibrato',440,880,0.3,0.2],
  win:['triangle',523,1046,0.5,0.2],
  lose:['noise',1200,90,0.6,0.2],
  step:['triangle',240,200,0.04,0.05]};
/* Repeats stay fresh (§14 事実 1): every playback shifts the whole sweep
   by one small random factor - well under the semitone (x1.06) that reads
   as a deliberate step - so a catch streak or a footstep run never sounds
   like the same sample twice. Both ends of the sweep move together, which
   keeps its interval, and the interval is the information (§14 事実 1 の
   第 3 形). Math.random, not the game's rand(): the board's seed must not
   be consumed by a sound. */
const SFX_JITTER=0.04;
/* The victory phrase (§2, C-1326): the win is the round's heaviest beat
   (C-1316), and one sweep undersold it. A rising major arpeggio - the
   sfxr powerUp shape - in plain C: no melody borrowed from anywhere,
   four notes a chord owns. One jitter factor for the whole phrase, so
   the fanfare stays in tune with itself. */
const WIN_NOTES=[523,659,784,1046];
function sfx(name){
  /* Zero is silence, not a very quiet sound. Scheduling one would hand
     exponentialRampToValueAtTime a start value of 0, which has no defined
     ramp, and would build a node graph for something nobody can hear. */
  if(MUTED||masterGain()<=0)return;
  const spec=SFX_TABLE[name];if(!spec)return;
  try{
    if(!AC){AC=new (window.AudioContext||window.webkitAudioContext)()}
    if(AC.state==='suspended'){AC.resume()}
    const t0=AC.currentTime,[wave,rawF0,rawF1,dur]=spec,vol=sfxGain(name);
    const jit=1+(Math.random()*2-1)*SFX_JITTER;
    const f0=rawF0*jit,f1=rawF1*jit;
    if(name==='win'){
      /* Each note passes through the same gain contract as any effect:
         the combat step, the ceiling, the master dial and M, per note. */
      WIN_NOTES.forEach((f,i)=>{
        const t1=t0+i*0.11,last=i===WIN_NOTES.length-1;
        const g=AC.createGain();
        g.gain.setValueAtTime(vol,t1);
        g.gain.exponentialRampToValueAtTime(0.001,t1+(last?0.34:0.16));
        g.connect(AC.destination);
        const osc=AC.createOscillator();osc.type='triangle';
        osc.frequency.setValueAtTime(f*jit,t1);
        osc.connect(g);osc.start(t1);osc.stop(t1+(last?0.4:0.22))});
      return}
    /* The gain first: it carries the volume the loudness judge reads, and
       it must be on the books whatever the source turns out to be. */
    const gain=AC.createGain();
    gain.gain.setValueAtTime(vol,t0);
    gain.gain.exponentialRampToValueAtTime(0.001,t0+dur);
    gain.connect(AC.destination);
    if(wave==='noise'){
      /* sfxr's explosion family is not a tone at all (§2): white noise
         through a low-pass that falls from f0 to f1. The buffer is built
         once and reused - half a second of noise outlives every effect. */
      if(!NOISE_BUF){const rate=AC.sampleRate||44100,len=(rate*0.5)|0;
        NOISE_BUF=AC.createBuffer(1,len,rate);
        const ch=NOISE_BUF.getChannelData(0);
        for(let i=0;i<ch.length;i++){ch[i]=Math.random()*2-1}}
      const src=AC.createBufferSource();src.buffer=NOISE_BUF;
      const lp=AC.createBiquadFilter();lp.type='lowpass';
      lp.frequency.setValueAtTime(f0,t0);
      lp.frequency.exponentialRampToValueAtTime(Math.max(1,f1),t0+dur);
      src.connect(lp);lp.connect(gain);
      src.start(t0);src.stop(t0+dur+0.02);
    }else{
      const osc=AC.createOscillator();
      osc.type=wave==='vibrato'?'sawtooth':wave;
      osc.frequency.setValueAtTime(f0,t0);
      osc.frequency.exponentialRampToValueAtTime(Math.max(1,f1),t0+dur);
      if(wave==='vibrato'){
        /* sfxr's powerUp is its own preset, not a louder pickup (§2,
           C-1339): a rising tone WITH vibrato - an LFO wired into the
           main oscillator's frequency. The depth is set by assignment,
           not scheduled, so the loudness books only ever carry gains
           that are loudness. */
        const lfo=AC.createOscillator(),dep=AC.createGain();
        lfo.frequency.setValueAtTime(6,t0);
        dep.gain.value=f0*0.04;
        lfo.connect(dep);dep.connect(osc.frequency);
        lfo.start(t0);lfo.stop(t0+dur+0.02);}
      osc.connect(gain);
      osc.start(t0);osc.stop(t0+dur+0.02);
    }
  }catch(err){/* no audio device is a machine, not a bug */}
}
"""

#: Drives a generated page in node with a recording AudioContext, so the
#: gain a fight actually plays at can be read back instead of grepped for.
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const played = [];
/* Which kind of source each effect built, so texture is a read fact: the
   explosion family should be noise through a falling low-pass, the
   melodic family an oscillator (§2, C-1308). */
const nodes = [];
function Recorder(){ this.state='running'; this.currentTime=0; this.destination={};
  this.sampleRate=44100 }
/* Starting frequencies, so the repeat variation is a read fact too: the
   same effect fired eight times must land on close-but-different pitches
   (§14, C-1317). */
const freqs = [];
Recorder.prototype.createOscillator = function(){
  return { type:'', frequency:{kind:'frequency',
             setValueAtTime(v){ freqs.push(v) }, exponentialRampToValueAtTime(){}},
           connect(){ nodes.push('oscillator') }, start(){}, stop(){} } };
Recorder.prototype.createBuffer = function(ch, len){
  return { getChannelData: () => new Float32Array(len) } };
/* Connections, not constructions: a filter that is built and then bypassed
   never shaped anything, so the record is what each node was wired INTO. */
Recorder.prototype.createBufferSource = function(){
  return { buffer:null, start(){}, stop(){},
    connect(t){ nodes.push(t && t.kind === 'lowpass' ? 'noise->lowpass' : 'noise->direct') } } };
Recorder.prototype.createBiquadFilter = function(){
  return { kind:'lowpass', type:'',
    frequency:{ setValueAtTime(){}, exponentialRampToValueAtTime(){} },
    connect(){ nodes.push('lowpass->out') } } };
Recorder.prototype.createGain = function(){
  /* A gain wired into an AudioParam is modulation depth, not loudness
     (§2, C-1339): the vibrato's LFO reaches the oscillator through one,
     and THAT connection - not the LFO's existence - is what makes the
     wobble audible. Recorded like the low-pass above: as a wiring fact. */
  const g = { gain:{ setValueAtTime(v){ played.push(v) },
                     exponentialRampToValueAtTime(){} },
    connect(t){ if (t && t.kind === 'frequency') nodes.push('lfo->frequency') } };
  return g };
globalThis.window = { AudioContext: Recorder };
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
const keyHandlers = [];
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') keyHandlers.push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function measure(fn){ played.length = 0; fn(); return played.slice() }
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn(i * 16) } }
/* Does this template turn the step on by itself? Read by playing it, not by
   grepping for the call: a `combat(true)` behind a condition that is never
   true is in the file and never in the fight. */
run(2);
keyHandlers.forEach(fn => fn({ key: ' ', code: 'Space', preventDefault(){}, stopImmediatePropagation(){} }));
run(120);
const combatDuringPlay = combatOn();
/* A template that only fights when something is near reports false above,
   and its opening room being quiet is the design. That is indistinguishable
   from a clause that can never fire unless the condition is met, so meet it:
   put an enemy on the hero and see whether the step comes on. */
let nearEnemy = null;
if (typeof enemies !== 'undefined' && typeof hero !== 'undefined' && !combatDuringPlay) {
  try {
    (enemies[room] || (enemies[room] = [])).push(
      { x: hero.x, y: hero.y, dx: 0, dy: 0, t: 0, alive: true });
    run(2);
    nearEnemy = combatOn();
  } catch (err) { nearEnemy = 'error: ' + err.message }
}
combat(false);
const calm = measure(() => sfx('hurt'));
combat(true);
const loud = measure(() => sfx('hurt'));
/* Mute has to win in combat too, or the step is a second mute. */
keyHandlers.forEach(fn => fn({ key: 'm', preventDefault(){}, stopImmediatePropagation(){} }));
const muted = measure(() => sfx('hurt'));
keyHandlers.forEach(fn => fn({ key: 'm', preventDefault(){}, stopImmediatePropagation(){} }));
combat(false);
const backToCalm = measure(() => sfx('hurt'));
/* Nothing may exceed the ceiling, however loud the fight gets. */
combat(true);
const peaks = Object.keys(SFX_TABLE).map(n => sfxGain(n));
combat(false);
/* Texture, as built: what nodes each family's effect actually created. */
nodes.length = 0; sfx('hurt'); const hurtNodes = nodes.slice();
nodes.length = 0; sfx('gem'); const gemNodes = nodes.slice();
/* The step-up, as wired (§2, C-1339): the powerup must carry its vibrato
   as a CONNECTION into the oscillator's frequency, the cheer must reach
   it, and the mute must silence it like everything else. */
nodes.length = 0; sfx('powerup'); const powerupNodes = nodes.slice();
let cheerNodes = null;
if (typeof comboCheer === 'function') {
  nodes.length = 0; comboCheer(); cheerNodes = nodes.slice() }
keyHandlers.forEach(fn => fn({ key: 'm', preventDefault(){}, stopImmediatePropagation(){} }));
nodes.length = 0; sfx('powerup'); const powerupMutedNodes = nodes.length;
keyHandlers.forEach(fn => fn({ key: 'm', preventDefault(){}, stopImmediatePropagation(){} }));
/* The repeat, as heard (§14, C-1317): the same effect eight times over.
   Each start frequency must sit near the table's pitch and the eight must
   not all be the same one - and the mute stops the variation with the
   sound, because there is no sound. */
freqs.length = 0;
for (let i = 0; i < 8; i++) sfx('catch');
const catchFreqs = freqs.slice();
keyHandlers.forEach(fn => fn({ key: 'm', preventDefault(){}, stopImmediatePropagation(){} }));
freqs.length = 0; sfx('catch'); const mutedFreqs = freqs.length;
keyHandlers.forEach(fn => fn({ key: 'm', preventDefault(){}, stopImmediatePropagation(){} }));
/* The victory phrase (§2, C-1326): a rising arpeggio, every note on the
   books, and silent under the mute like everything else. */
freqs.length = 0; played.length = 0;
sfx('win');
const winFreqs = freqs.slice(), winGains = played.length;
keyHandlers.forEach(fn => fn({ key: 'm', preventDefault(){}, stopImmediatePropagation(){} }));
freqs.length = 0; sfx('win'); const winMutedFreqs = freqs.length;
keyHandlers.forEach(fn => fn({ key: 'm', preventDefault(){}, stopImmediatePropagation(){} }));
console.log(JSON.stringify({
  calm: calm[0] ?? null, loud: loud[0] ?? null,
  mutedPlayed: muted.length, backToCalm: backToCalm[0] ?? null,
  peak: Math.max.apply(null, peaks), hasCombat: typeof combat === 'function',
  combatDuringPlay: combatDuringPlay, nearEnemy: nearEnemy,
  hurtNodes: hurtNodes, gemNodes: gemNodes,
  powerupNodes: powerupNodes, cheerNodes: cheerNodes,
  powerupMutedNodes: powerupMutedNodes,
  catchFreqs: catchFreqs, mutedFreqs: mutedFreqs,
  winFreqs: winFreqs, winGains: winGains, winMutedFreqs: winMutedFreqs,
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so its gains can be recorded in node."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


#: The volume dial, measured on a page that was opened with the slider
#: already at a value - which is the path a person's setting actually
#: takes, through storage and back out on the next load.
VOLUME_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const keyHandlers = [];
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { if (type === 'keydown') keyHandlers.push(fn) };
globalThis.Image = function(){ return nothing };
/* Any tuning key answers with the stored panel, so the probe does not have
   to know which template it is driving. */
const writes = [];
const storedPanel = STORED_INPUT;
globalThis.localStorage = {
  getItem: (k) => (k.indexOf('sidra.tune.') === 0 ? JSON.stringify(storedPanel) : null),
  setItem: (k, v) => { writes.push([k, v]) },
  removeItem: () => {} };
const played = [];
class Ctx {
  constructor(){ this.currentTime = 0; this.sampleRate = 44100; this.state = 'running' }
  resume(){}
  createGain(){ const g = { gain: {
    setValueAtTime: (v) => { played.push(v) },
    exponentialRampToValueAtTime: () => {},
    linearRampToValueAtTime: () => {} }, connect(){} }; return g }
  createOscillator(){ return { frequency: { setValueAtTime(){}, exponentialRampToValueAtTime(){} },
    connect(){}, start(){}, stop(){}, type: '' } }
  createBufferSource(){ return { connect(){}, start(){}, stop(){}, buffer: null } }
  createBiquadFilter(){ return { frequency: { setValueAtTime(){},
    exponentialRampToValueAtTime(){} }, connect(){}, type: '' } }
  createBuffer(_c, len){ return { getChannelData: () => new Float32Array(len) } }
  get destination(){ return { } }
}
globalThis.window = globalThis;
globalThis.AudioContext = Ctx;
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function measure(fn){ played.length = 0; fn(); return played.slice() }
function press(k){ keyHandlers.forEach(fn => fn({ key: k, code: k,
  preventDefault(){}, stopImmediatePropagation(){} })) }
combat(false);
const calm = measure(() => sfx('hurt'));
combat(true);
const loud = measure(() => sfx('hurt'));
combat(false);
/* The fight's step has to be read on a sound the ceiling actually binds,
   or the ordering of the dial and the clamp cannot show. 'hurt' peaks at
   0.48 in combat and never reaches MAX_GAIN, so moving the dial to the
   wrong side of Math.min leaves its ratio at exactly 2 either way - which
   is how a first version of this probe passed a page whose ratio really
   did depend on the slider. 'lose' clamps: 0.6 calm, 0.9 in the fight. */
const calmClamped = measure(() => sfx('lose'));
combat(true);
const loudClamped = measure(() => sfx('lose'));
combat(false);
/* The dial and the mute are different controls: M silences a page at any
   volume, and releasing it hands back the volume that was set. */
press('m');
const whileMuted = measure(() => sfx('hurt'));
press('m');
const afterMute = measure(() => sfx('hurt'));
/* The music rides the same dial. */
const tune = measure(() => musicNote(440, 0, 0.2, 0.2, 'square'));
/* The one place the ceiling can actually be reached. Nothing the product
   ships comes near MAX_GAIN - the loudest effect peaks at 0.48 against a
   0.9 ceiling - so with the shipped values the dial's position relative to
   Math.min makes no difference at all, and a ratio read off any real sound
   cannot tell the two orderings apart. musicNote takes its gain from the
   caller, so asking it for one the clamp does bind is the only way to
   measure the rule rather than assume it. */
combat(true);
const clampedTune = measure(() => musicNote(440, 0, 0.2, 0.8, 'square'));
combat(false);
console.log(JSON.stringify({
  volume: tuneNum('volume', 100), master: masterGain(),
  calm: calm[0] ?? null, loud: loud[0] ?? null,
  calmClamped: calmClamped[0] ?? null, loudClamped: loudClamped[0] ?? null,
  mutedPlayed: whileMuted.length, afterMute: afterMute[0] ?? null,
  tune: tune[0] ?? null, tuneCount: tune.length,
  clampedTune: clampedTune[0] ?? null,
  stored: tuneFacts().values.volume,
}));
"""


def volume_probe_source(script: str, *, volume: int) -> str:
    """Open the page with the slider already at ``volume`` and listen."""

    return VOLUME_PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "STORED_INPUT", json.dumps({"volume": volume})
    )


__all__ = [
    "COMBAT_GAIN",
    "MAX_GAIN",
    "PREAMBLE_NAMES",
    "PROBE",
    "SFX_PREAMBLE",
    "VOLUME_PROBE",
    "probe_source",
    "volume_probe_source",
]
