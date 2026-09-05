"""The result strip says, in one line, why this go ended.

§8 wants the strip to make the next attempt attractive; §11 says the way
to do that honestly is to hand the player a measurement rather than a
verdict. The losing strip currently offers only 「R / タップでもう一度」 -
it asks for another go without saying what went wrong, which is the one
thing that would make the next go different.

Everything here is read off counters the round already keeps. Nothing is
inferred, estimated, or phrased as advice:

* **A cause counted zero is never named.** 「被弾 0 回」 on a result strip
  is worse than silence, and a cause the page cannot count is not written
  down at all.
* **One line, the largest cause.** A list of everything that went wrong is
  a scolding; the biggest number is the thing to fix first.
* **Only on a loss.** A win that explains itself is second-guessing
  somebody who has just succeeded.
* **Counted, not judged.** The line reports a number and, where the
  template knows it, the shape of the mistake. It never tells the player
  what to do instead: the counters do not know that.

Written per template because the counters are - there is no shared "times
you were hit", and inventing one would mean rewriting ten games. The
expressions are substituted into the page as source, the way
``ROUND_SCORE`` has been since C-1104, so nothing here needs ``eval`` and a
renamed counter breaks the judge rather than silently blanking the line.
"""

from __future__ import annotations

import json

#: Per template: how the page knows this go was lost, and the causes it can
#: count. Each cause is ``(count expression, line expression)``; the line
#: expression is JavaScript that builds the sentence from ``n``, the count.
#: Both are spliced into the page as source.
LOSS_WIRED: dict[str, dict] = {
    # Three hull hits end the run, so the hull count is the whole story,
    # and the wave says how far it got before they ran out.
    "shooter": {
        "lost": "state==='over'",
        "causes": [
            ("3-ship.hp", "'被弾 '+n+' 回——第 '+wave+' 波まで持ちこたえた'"),
        ],
    },
    # The marble already writes its own reason down when it stops. Reading
    # that is better than deciding a second time and risking two answers.
    "marble": {
        "lost": "state==='over'&&over!=='コースを走り切った。'",
        "causes": [("1", "over+'ゲートを '+score+' 点ぶん抜けたところだった'")],
    },
    # Falls are counted because the checkpoint needs them. A run that never
    # fell simply ran out of clock, and that is not this line's business.
    "platformer": {
        "lost": "state!=='goal'",
        "causes": [
            ("respawns", "'落下 '+n+' 回——そのたび最後の足場からやり直している'"),
        ],
    },
    # Three head hits win it, so the shortfall in head hits is exactly how
    # far off the go was.
    "kaiju": {
        "lost": "state!=='won'",
        "causes": [
            ("3-cycles", "'頭部にあと '+n+' 発——脚を崩した直後だけ頭が下がる'"),
        ],
    },
    # 'end' is reached by winning and by losing alike, so the hp
    # comparison is what tells them apart (C-1422): at the end one side is
    # at zero, and it is the player's side that makes this a loss.
    #
    # Two causes rather than one, because duel has two genuinely different
    # ways to lose a heart and they call for different things: a beam that
    # landed was fired into the lane the player was standing in, and a lost
    # clash was a shove that did not push hard enough. Both are stated as
    # what happened - never as what to do instead.
    "duel": {
        "lost": "state==='end'&&p.hp<e.hp",
        "causes": [
            ("lostBeam", "'ビームを '+n+' 発——撃たれた瞬間に同じレーンに居た'"),
            (
                "lostClash",
                "'つばぜり合いに '+n+' 回負けた——連打がひかりの溜めに届かなかった'",
            ),
        ],
    },
    # Two causes, because the adventure has two damage sites and they are
    # different mistakes (C-1425): a roamer is something that closed the
    # distance while the hero was busy, the guardian is a blow that was
    # telegraphed and landed anyway. Neither is advice - the counter says
    # what happened and the clause says what the thing does.
    #
    # A loss here is only reachable by something that can find a route
    # (C-1424), so unlike the others this template's losing go is driven
    # rather than held: see ``probe_source``'s ``route``.
    "adventure": {
        "lost": "state==='over'",
        "causes": [
            ("hurtRoam", "'まものに '+n+' 回やられた——近づくと追ってくる'"),
            ("hurtGuard", "'番人の一撃を '+n+' 回——溜めの光のあとに来る'"),
        ],
    },
    # Laps are the score here, so the shortfall is the reason.
    "racing": {
        "lost": "state!=='goal'",
        "causes": [
            ("LAPS-times.length", "'あと '+n+' 周——障害物に当たるたび速度が落ちる'"),
        ],
    },
}

#: Why the rest say nothing. A template with no losing state has no loss to
#: explain, which is a different answer from "not yet".
LOSS_UNWIRED: dict[str, str] = {
    "catch": "no losing state at all - the clock ends every go and the score is the whole verdict",
    "fishing": "same as catch: nothing can end the round early",
    "puzzle": "'over' means the board jammed, but nothing counts *why* it jammed yet",
}

#: Names the preamble introduces.
PREAMBLE_NAMES: tuple[str, ...] = ("recapLost", "recapOver", "recapLine", "recapFacts")

_UNWIRED_PREAMBLE = """
/* --- why this go ended: not wired for this template ------------------ */
function recapOver(){return false}
function recapLost(){return false}
function recapLine(){return ''}
function recapFacts(){return {lost:false,line:'',wired:false}}
"""

_WIRED_PREAMBLE = """
/* --- why this go ended, in one line (§8 / §11) ----------------------- */
/* Guarded throughout: the strip is drawn over whatever ended the round,
   including a clock that fired before the template ran its own reset, and
   a line that threw would take the restart hint down with it. */
/* The go has to be *finished* before anything is said about why it ended.
   Two of the wired conditions are "did not reach the winning state", which
   is true from the first frame - and without this guard the page would be
   holding a verdict about a round still being played. The predicate is the
   same one the result strip itself draws on, so the line can never appear
   on a screen the strip is not on. */
function recapOver(){try{
  if(typeof ROUND_DONE!=='undefined'&&ROUND_DONE)return true;
  return (typeof roundEnded==='function')?!!roundEnded():false}
  catch(e){return false}}
function recapLost(){if(!recapOver())return false;
  try{return !!(RECAP_LOST_TOKEN)}catch(e){return false}}
function recapCauses(){const out=[];
RECAP_CAUSES_TOKEN
  return out}
/* The largest counted cause, or nothing at all. A cause at zero is not a
   cause, and a strip that says 「0 回」 is worse than one that says
   nothing. */
function recapLine(){if(!recapLost())return '';
  let best=null;
  recapCauses().forEach(function(c){
    if(!isFinite(c.n)||c.n<=0)return;
    if(best===null||c.n>best.n){best=c}});
  return best?best.say:''}
function recapFacts(){return {lost:recapLost(),line:recapLine(),wired:true}}
"""

#: One cause, as source: count it, then build its sentence from the count.
_CAUSE = """  try{const n=Number(COUNT_TOKEN);
    out.push({n:n,say:isFinite(n)&&n>0?(LINE_TOKEN):''})}catch(e){}
"""


def preamble_for(template: str) -> str:
    """The rule, told this template's own counters - or told there are none."""

    spec = LOSS_WIRED.get(template)
    if not spec:
        return _UNWIRED_PREAMBLE
    causes = "".join(
        _CAUSE.replace("COUNT_TOKEN", count).replace("LINE_TOKEN", line)
        for count, line in spec["causes"]
    )
    return _WIRED_PREAMBLE.replace("RECAP_LOST_TOKEN", spec["lost"]).replace(
        "RECAP_CAUSES_TOKEN", causes.rstrip("\n")
    )




#: The probe. Plays a real go with nobody touching it - which loses, in
#: every wired template - and reads the line off the page, then asks the
#: same page what it would say after a win and with the counters at zero.
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let clock = 0;
globalThis.performance = { now: () => clock };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
const storedPanel = STORED_INPUT;
globalThis.localStorage = {
  getItem: (k) => (storedPanel && k.indexOf('sidra.tune.') === 0
    ? JSON.stringify(storedPanel) : null),
  setItem: () => {}, removeItem: () => {} };
let drawn = [];
const ctx = new Proxy({ fillText: (t) => { drawn.push(String(t)) } },
  { get: (t, k) => (k in t ? t[k] : (k === Symbol.toPrimitive ? () => 0 : nothing)),
    set: () => true });
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => ctx }) };
globalThis.location = { reload: () => {} };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function run(n){ for (let i = 0; i < n && queued; i++) {
  const fn = queued; queued = null; clock += 50 / 3; fn(clock) } }
function press(k){ (handlers['keydown'] || []).forEach(fn => fn({ key: k,
  code: k === ' ' ? 'Space' : k, preventDefault(){}, stopImmediatePropagation(){} })) }
/* Letting go again. A held key never needed this; a route does, because
   walking a corner means stopping pressing the way you came. */
function release(k){ (handlers['keyup'] || []).forEach(fn => fn({ key: k,
  code: k === ' ' ? 'Space' : k, preventDefault(){}, stopImmediatePropagation(){} })) }
run(2); press(' '); run(2);
/* A template whose loss has to be *driven* rather than held installs its
   own steering here, and the frame loop below calls ROUTE_STEP. Empty for
   every template that loses on its own. */
ROUTE_SETUP_TOKEN
/* HOLD_INPUT is a key held down for the whole go, which is how the two
   templates that need a *mistake* rather than a shortfall get one: an
   untouched platformer never falls, so it has no counted cause and
   correctly says nothing. */
const held = HOLD_INPUT;
if (held) { press(held) }
let lost = null, verdictWhileLive = false;
for (let f = 0; f < FRAMES_INPUT; f++) {
  if (held) { press(held) }
  ROUTE_STEP_TOKEN
  run(1);
  /* A verdict handed down mid-play is the failure the round-over guard
     exists for, and it is invisible if only the end is inspected. */
  if (recapLost() && !recapOver()) { verdictWhileLive = true }
  if (lost === null && recapFacts().lost) { lost = recapFacts() }
}
/* Raw counters, read straight off the page rather than through the table
   the line is built from - so a line whose number was invented instead of
   counted disagrees with them. */
function peek(name){ try { return eval(name) } catch (e) { return null } }
const counters = { hp: peek('ship&&ship.hp'), respawns: peek('respawns'),
  cycles: peek('cycles'), laps: peek('times&&times.length'),
  /* duel's two, and the hp comparison that says which side lost. */
  lostBeam: peek('lostBeam'), lostClash: peek('lostClash'),
  pHp: peek('p&&p.hp'), eHp: peek('e&&e.hp'),
  /* adventure's two damage sites, read off the page rather than through
     hurtFacts, so a facts function that lies disagrees with them. */
  hurtRoam: peek('hurtRoam'), hurtGuard: peek('hurtGuard'),
  heroHp: peek('hero&&hero.hp') };
const atEnd = recapFacts();
/* The strip as drawn, after the round is over. */
drawn = [];
run(4);
const strip = drawn.slice();
/* The same page, asked what it would say about a win. The predicate is
   the product rule, so it is the thing to interrogate - not a second
   implementation of it out here. */
let afterWin = null;
try { state = WIN_STATE_INPUT; afterWin = recapFacts() } catch (e) { afterWin = 'error: ' + e.message }
console.log(JSON.stringify({
  lost: lost, atEnd: atEnd, strip: strip, afterWin: afterWin,
  verdictWhileLive: verdictWhileLive, counters: counters,
}));
"""

#: What a win looks like to each wired template, for the half of the check
#: that asks whether the line stays quiet.
WIN_STATE: dict[str, str] = {
    "shooter": "play",
    # 'end' is both outcomes here, so a win is the same state with the hp
    # comparison the other way round. The probe sets the state; the loss
    # predicate is what has to stay quiet, and it reads p.hp against e.hp.
    "duel": "play",
    "marble": "roll",
    "platformer": "goal",
    "kaiju": "won",
    "racing": "goal",
    "adventure": "win",
}


def probe_source(
    script: str,
    *,
    template: str,
    frames: int = 4200,
    hold: str | None = None,
    stored: dict | None = None,
    route: tuple[str, str] | None = None,
) -> str:
    """Play a go, then ask the same page what it would say about a win.

    ``hold`` presses one key for the whole round, and ``stored`` opens the
    page with a panel value already set - both are how a losing go is
    produced for the templates an untouched run does not lose: since
    C-1404 every racing rung finishes without input, so its loss comes
    from the panel's own slow pace, the way C-1105 generates one.

    ``route`` is the third way, for a template that neither loses by itself
    nor loses to any one held key: ``(setup, step)`` is JavaScript spliced
    in after the page and into the frame loop, so the go is *steered*. The
    adventure is the only one - it cannot be lost without finding a way out
    of the first room, which C-1424 had to measure before this line could
    exist. The step runs before the frame it steers, so ``f`` is the frame
    about to be drawn.
    """

    setup, step = route or ("", "")
    return (
        PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("ROUTE_SETUP_TOKEN", setup)
        .replace("ROUTE_STEP_TOKEN", step)
        .replace("FRAMES_INPUT", str(int(frames)))
        .replace("HOLD_INPUT", json.dumps(hold))
        .replace("STORED_INPUT", json.dumps(stored))
        .replace("WIN_STATE_INPUT", json.dumps(WIN_STATE.get(template, "play")))
    )


__all__ = [
    "LOSS_UNWIRED",
    "LOSS_WIRED",
    "PREAMBLE_NAMES",
    "WIN_STATE",
    "preamble_for",
    "probe_source",
]
