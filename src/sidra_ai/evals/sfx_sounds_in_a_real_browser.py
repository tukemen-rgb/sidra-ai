"""Do the effects actually sound in a real browser?

C-1974, §2. The whole sound of a SIDRA game is synthesised in the page -
no files are shipped, every voice is built out of oscillators, a noise
buffer and gains. Nine judges read that sound, and all nine of them drive
a hand-written stand-in::

    globalThis.window = { AudioContext: Recorder };

**Why this needs a real browser.** The stand-in accepts everything. Give it
an oscillator type Web Audio does not have, ramp a gain from zero, hand
``createPeriodicWave`` an array that is too short - it records the call and
the judge stays green. A real browser refuses each of those, and the page
wraps every voice in ``try{}catch(e){}`` because a machine with no audio
device is not a bug. Put the two together and a refused voice disappears
without a sound, a warning, or a red number.

So this opens the page once in real headless Chromium, with the real
``AudioContext``, and counts the voices that reach ``start()``:

* each name in ``SFX_TABLE`` played through the page's own ``sfx()``,
* the engine voice (``engineTick``), which is a continuously running
  oscillator rather than a one-shot, and
* the music bed (``musicArm`` + ``musicTick``), which schedules ahead.

The counters wrap the real prototypes and re-throw, so the page behaves
exactly as it does for a visitor; what they add is a record of what the
browser was actually asked for, and what it refused.

**What this cannot measure.** That the first press is what starts the
sound. A synthetic ``KeyboardEvent`` is not user activation, so without
``--autoplay-policy=no-user-gesture-required`` the context stays
``suspended`` no matter how correct the page is (measured: ``state`` is
``suspended`` and ``currentTime`` never leaves 0). The flag puts the
context in the state a real press produces; the press itself needs a
driver.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.audio import SFX_PREAMBLE
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.probekeys import with_probe_keys
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

ASK = "ふくろうのキャッチゲームを作って"

#: Chromium's own switch. A synthetic key press is not user activation, so
#: without it every voice is scheduled onto a context that never runs - a
#: correct page and a broken one would read the same.
AUTOPLAY_FLAG = "--autoplay-policy=no-user-gesture-required"

#: The two voices that are not in the effect table: the engine is held
#: open across frames, and the music bed schedules ahead of the clock.
HELD_VOICES = ("engine", "music")

_TITLE = re.compile(r"<title>SFXREAL(.*?)</title>", re.S)
_TABLE = re.compile(r"const SFX_TABLE=\{(.*?)\]\};", re.S)
_NAME = re.compile(r"^\s*(\w+):\[", re.M)

#: Counts what the browser was really asked for, and re-throws so the page
#: behaves exactly as it does for a visitor. Placed before the page's own
#: scripts so the first voice is counted too.
_HOOK = """
<script>
window.__SFX = {started: 0, refused: []};
(function(){
  const C = window.AudioContext || window.webkitAudioContext;
  if (!C) { window.__SFX.refused.push('this browser has no AudioContext'); return }
  ['OscillatorNode', 'AudioBufferSourceNode'].forEach(function(name){
    const node = window[name];
    if (!node) { window.__SFX.refused.push('no ' + name); return }
    const start = node.prototype.start;
    node.prototype.start = function(){
      window.__SFX.started++;
      try { return start.apply(this, arguments) }
      catch (e) {
        window.__SFX.refused.push(name + '.start: ' + String(e).slice(0, 70));
        throw e } };
  });
  ['createOscillator', 'createBufferSource', 'createPeriodicWave',
   'createBiquadFilter', 'createGain', 'createStereoPanner'].forEach(function(m){
    const made = C.prototype[m];
    if (!made) return;
    C.prototype[m] = function(){
      try { return made.apply(this, arguments) }
      catch (e) {
        window.__SFX.refused.push(m + ': ' + String(e).slice(0, 70));
        throw e } };
  });
})();
</script>
"""

_REPORT = """
<script>
PROBE_KEYS_PLACEHOLDER
addEventListener('load', function(){
  setTimeout(function(){
    const out = {sounded: [], silent: [], refused: []};
    try {
      /* The pair comes from probekeys, not from here (C-1651's ratchet):
         a hand-written {key:' ', code:' '} presses a key no template
         listens for, and the gesture the sound waits on never happens. */
      const pair = probeKey(' ');
      const press = new KeyboardEvent('keydown',
        {key: pair.key, code: pair.code, bubbles: true});
      document.dispatchEvent(press); window.dispatchEvent(press);
      Object.keys(SFX_TABLE).forEach(function(name){
        const before = window.__SFX.started;
        try { sfx(name) } catch (e) {
          window.__SFX.refused.push(name + ' threw ' + String(e).slice(0, 60)) }
        (window.__SFX.started > before ? out.sounded : out.silent).push(name);
      });
      const held = window.__SFX.started;
      try { engineTick(0.5) } catch (e) {
        window.__SFX.refused.push('engine threw ' + String(e).slice(0, 60)) }
      const on = (typeof engineFacts === 'function') && engineFacts().on;
      (window.__SFX.started > held && on ? out.sounded : out.silent).push('engine');
      try { musicArm(); musicTick(16); musicTick(400) } catch (e) {
        window.__SFX.refused.push('music threw ' + String(e).slice(0, 60)) }
      const bars = (typeof musicFacts === 'function') ? musicFacts().scheduled : 0;
      (bars > 0 ? out.sounded : out.silent).push('music');
      out.refused = window.__SFX.refused.slice(0, 6);
      out.state = (typeof AC !== 'undefined' && AC) ? AC.state : null;
      out.rate = (typeof AC !== 'undefined' && AC) ? AC.sampleRate : null;
      out.real = (typeof AC !== 'undefined' && AC) ? AC.constructor.name : null;
    } catch (e) { out.err = String(e).slice(0, 120) }
    document.title = 'SFXREAL' + JSON.stringify(out);
  }, 800);
});
</script>
"""


@dataclass(frozen=True)
class RealSoundResult:
    voices_that_sound: int
    voices_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def effect_names() -> tuple[str, ...]:
    """The effect table as the page will see it, read from its own source."""
    body = _TABLE.search(SFX_PREAMBLE)
    if body is None:  # pragma: no cover - the table is part of the page
        raise RuntimeError("sfx_sounds_in_a_real_browser: no SFX_TABLE in the page")
    return tuple(_NAME.findall(body.group(1)))


def _open(html: str) -> dict:
    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    with tempfile.TemporaryDirectory() as room:
        page = pathlib.Path(room) / "page.html"
        page.write_text(
            html.replace("<body", _HOOK + "<body", 1).replace(
                "</body>", with_probe_keys(_REPORT) + "</body>"
            ),
            encoding="utf-8",
        )
        run = subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                AUTOPLAY_FLAG,
                "--virtual-time-budget=8000",
                "--window-size=390,844",
                "--dump-dom",
                f"file://{page}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    found = _TITLE.search(run.stdout)
    return json.loads(found.group(1)) if found else {"err": "the page said nothing"}


def evaluate_sfx_sounds_in_a_real_browser() -> RealSoundResult:
    wanted = effect_names() + HELD_VOICES
    total = len(wanted)
    seen = _open(generate_game(ASK).html)
    if "err" in seen:
        return RealSoundResult(0, total, (str(seen["err"]),))

    sounded = set(seen.get("sounded", ()))
    failures = [f"{name}: nothing started in a real browser" for name in wanted
                if name not in sounded]
    failures += [f"the browser refused {line}" for line in seen.get("refused", ())]
    strangers = sorted(sounded - set(wanted))
    if strangers:
        failures.append("the page sounded a voice the table does not name: "
                        + ", ".join(strangers))
    readings = (
        f"{len(sounded & set(wanted))}/{total} voices started",
        f"context={seen.get('real')} state={seen.get('state')} rate={seen.get('rate')}",
    )
    return RealSoundResult(
        voices_that_sound=len(sounded & set(wanted)),
        voices_total=total,
        failures=tuple(failures[:4]),
        readings=readings,
    )


__all__ = [
    "ASK",
    "AUTOPLAY_FLAG",
    "HELD_VOICES",
    "RealSoundResult",
    "effect_names",
    "evaluate_sfx_sounds_in_a_real_browser",
]
