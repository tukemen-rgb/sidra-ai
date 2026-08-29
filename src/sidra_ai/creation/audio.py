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
"""

from __future__ import annotations

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
    "win",
    "lose",
    "step",
)

#: Each effect is (wave, start Hz, end Hz, duration s, gain). The numbers
#: follow the sfxr preset shapes described in the knowledge base: pickups
#: rise, lasers fall fast, hurt is a low square drop, explosions are noise.
SFX_PREAMBLE = """
let AC=null,MUTED=false;
addEventListener('keydown',e=>{if(e.key==='m'||e.key==='M'){MUTED=!MUTED}});
const SFX_TABLE={
  sword:['square',420,180,0.09,0.18],
  cut:['triangle',700,320,0.08,0.2],
  gem:['square',660,1320,0.12,0.16],
  key:['triangle',520,1040,0.18,0.2],
  hurt:['square',200,70,0.22,0.24],
  fire:['sawtooth',900,140,0.3,0.2],
  charge:['sawtooth',120,480,0.25,0.1],
  clash:['square',300,260,0.06,0.12],
  catch:['triangle',500,900,0.09,0.16],
  win:['triangle',523,1046,0.5,0.2],
  lose:['sawtooth',300,80,0.6,0.2],
  step:['triangle',240,200,0.04,0.05]};
function sfx(name){
  if(MUTED)return;
  const spec=SFX_TABLE[name];if(!spec)return;
  try{
    if(!AC){AC=new (window.AudioContext||window.webkitAudioContext)()}
    if(AC.state==='suspended'){AC.resume()}
    const t0=AC.currentTime,[wave,f0,f1,dur,vol]=spec;
    const osc=AC.createOscillator(),gain=AC.createGain();
    osc.type=wave;
    osc.frequency.setValueAtTime(f0,t0);
    osc.frequency.exponentialRampToValueAtTime(Math.max(1,f1),t0+dur);
    gain.gain.setValueAtTime(vol,t0);
    gain.gain.exponentialRampToValueAtTime(0.001,t0+dur);
    osc.connect(gain);gain.connect(AC.destination);
    osc.start(t0);osc.stop(t0+dur+0.02);
  }catch(err){/* no audio device is a machine, not a bug */}
}
"""

__all__ = ["PREAMBLE_NAMES", "SFX_PREAMBLE"]
