"""The first ten seconds have to contain one win.

§8 事実 5・8 of the play notes: what decides whether a person plays a
second round is whether the first one gave them anything. A game whose
opening is as hard as its middle asks for patience before it has earned
any, and the generated pages had no rule about their first ten seconds at
all - the fishing marker started wherever the loop happened to be, the
first foe was the same size as the last.

The claim is about a *player*, so the judge is a player: a masher. It
presses the action, it wobbles left and right, it taps the canvas, and it
knows nothing about any particular game. If ten seconds of that produces
no success, the opening is asking for skill the person does not have yet.

``FIRST_SUCCESS`` is what counts as a win in each template's own terms,
and it is deliberately not the score: the score is what the result screen
shows at the end (C-1106), and for a race that is a completed lap - about
eighteen seconds away, and no use as a first taste.
"""

from __future__ import annotations

import json

#: How long the opening is, in seconds. §8's number.
OPENING_SECONDS = 10

#: The first win, as an expression the page can evaluate, and what it is
#: in words. Every one is an event the player caused - a catch, a kill, a
#: gem picked up - and not merely time passing.
FIRST_SUCCESS: dict[str, tuple[str, str]] = {
    "adventure": ("hero.gems>=1", "宝石を 1 個拾う"),
    "catch": ("score>=1", "1 個受け止める"),
    "duel": ("3-e.hp>=1", "1 発当てる"),
    "fishing": ("score>=1", "1 匹釣る"),
    "kaiju": ("boss.legHp<LEGHP", "脚に一撃入れる"),
    "platformer": ("me.gems>=1", "宝石を 1 個拾う"),
    "puzzle": ("score>=1", "1 手消す"),
    # Not a lap: a lap is eighteen seconds away and useless as a first
    # taste. Getting past the first obstacle is the thing a new driver
    # notices they did.
    "racing": ("passed>=1", "最初の障害物を抜ける"),
    "shooter": ("score>=1", "1 機落とす"),
}


#: A player who knows nothing. Presses the action, wobbles, taps - and
#: that is all. Anything cleverer would be measuring our own knowledge of
#: the template rather than the opening's generosity.
PROBE = """
const openNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : openNothing),
  apply: () => openNothing, set: () => true });
const openKeys = [], openUps = [], openPointers = [];
let openClock = 0;
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => openClock };
globalThis.addEventListener = (type, fn) => {
  if (type === 'keydown') openKeys.push(fn);
  if (type === 'keyup') openUps.push(fn) };
globalThis.Image = function(){ return openNothing };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.location = { reload: () => {} };
globalThis.document = { readyState: 'complete',
  createElement: () => openNothing, querySelector: () => null,
  getElementById: () => ({
    width: 720, height: 320, style: {},
    addEventListener: (type, fn) => { if (type === 'pointerdown') openPointers.push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => openNothing }) };
let openQueued = null;
globalThis.requestAnimationFrame = (fn) => { openQueued = fn; return 1 };
SCRIPT_PLACEHOLDER
function openPress(key, code){
  const ev = { key: key, code: code, clientX: 360, clientY: 160,
    pointerType: 'touch', pointerId: 1,
    preventDefault(){}, stopImmediatePropagation(){} };
  openKeys.forEach(fn => fn(ev));
  return ev }
function openRelease(ev){ openUps.forEach(fn => fn(ev)) }
function openTap(){ openPointers.forEach(fn => fn({ pointerType: 'touch',
  pointerId: 1, clientX: 360, clientY: 160,
  preventDefault(){}, stopImmediatePropagation(){} })) }
function openWin(){ try { return !!(SUCCESS_TOKEN) } catch (e) { return false } }
/* Already true before anyone played? Then it is not a success, it is a
   mistake in the expression - and the number would be measuring nothing. */
const openAtStart = openWin();
/* One press to get past the title screen, then the masher. */
openRelease(openPress(' ', 'Space'));
let openFirst = null, openFrames = 0;
const OPEN_LIMIT = Math.round(LIMIT_TOKEN * 60);
/* A slow masher, not a bot: the action about four times a second, and a
   direction *held* for half a second at a time before switching. Holding
   matters - a person leans on the key, and a tap-and-release model would
   measure a player nobody is instead of a generous opening. */
const OPEN_DIRS = ['ArrowRight', 'ArrowLeft'];
let openHeld = null;
for (let f = 0; f < OPEN_LIMIT && openQueued; f++) {
  if (f % 30 === 0) {
    if (openHeld) { openRelease(openHeld) }
    const dir = OPEN_DIRS[(f / 30) % 2];
    openHeld = openPress(dir, dir);
  }
  if (f % 15 === 0) {
    openRelease(openPress(' ', 'Space'));
    openTap();
  }
  const fn = openQueued; openQueued = null;
  openClock += 50 / 3;
  fn(openClock);
  openFrames = f + 1;
  if (openFirst === null && openWin()) { openFirst = openClock }
}
console.log(JSON.stringify({
  firstWinMs: openFirst, frames: openFrames, wonBeforePlaying: openAtStart,
  limitMs: OPEN_LIMIT * 50 / 3, running: openQueued !== null,
}));
"""


def probe_source(script: str, template: str, *, seconds: int = OPENING_SECONDS) -> str:
    """The page, played by someone who has never seen it."""

    expression = FIRST_SUCCESS.get(template, ("false", ""))[0]
    return (
        PROBE.replace("SUCCESS_TOKEN", expression)
        .replace("LIMIT_TOKEN", json.dumps(seconds))
        .replace("SCRIPT_PLACEHOLDER", script)
    )


__all__ = ["FIRST_SUCCESS", "OPENING_SECONDS", "PROBE", "probe_source"]
