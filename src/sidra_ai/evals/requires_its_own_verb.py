"""Can the game be won by somebody who never uses its own action?

§34 事実 1 (arXiv:1807.06734, Green/Khalifa/Barros/Nealen/Togelius 2018) gives
the formal test for 「this level teaches this mechanic」: **an agent that cannot
perform the action must not be able to beat it.** The paper evolves Mario
levels and runs a perfect A* agent crippled in one specific way - it cannot
jump high, it cannot see enemies - and asks whether the level becomes
unbeatable. If it does, the level requires that mechanic, and a player who
finishes it has been taught it by playing rather than by being told.

That is the destruction test this repository already runs every cycle, aimed
at the product instead of at the judge.

SIDRA needed it. §8 事実 8 says 「教えるのは説明でなく成功体験で」, and the
product answers with three lines of text on the title screen (C-1111) and a
guaranteed success in the first ten seconds (C-1108). Both are real, and
neither asks the question this one does: **is the verb necessary at all?**

**§34 事実 2 is why this judge counts to four and not to ten.** The paper is
explicit that the crippled agent has to be competent otherwise - theirs was a
perfect solver - because a bad agent's failure proves nothing: it lost, and
nobody can say whether that was the missing ability or the badness. Measured
before this module existed, an agent that only alternates the arrow keys and
taps space decided four of the ten templates and could not decide the other
six. Those six are named in ``VERB_UNDECIDABLE`` with the reason, and the
reason is about the measurement, never about the template: three of them use
the arrow keys AS the verb, two are not finished by a wanderer inside a round,
and one scores the same either way for reasons a walker cannot separate.

Writing them down as 「not required」 would be the more flattering number and a
false one.

Both directions are checked for each of the four. Without the second, an
implementation that scored zero for everybody would be perfect: the agent WITH
the verb has to get somewhere, or 「the verb matters」 is being read off two
failures.
"""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: Frames after the gate, at 60fps - a round and a bit. Long enough for the
#: four decided templates to separate, short enough that eight of these run
#: inside the collector's budget.
FRAMES = 1800

#: The templates whose own action can be withheld, and how.
#:
#: ``kind`` says what the verb IS, because that decides what crippling the
#: agent means. ``"space"`` templates are paced left and right in both runs
#: and only the action key is taken away. ``"steer"`` templates have no
#: separate action - the arrow keys ARE the verb - so the crippled run
#: presses nothing at all while the able run steers.
#:
#: C-1885: the three ``"steer"`` templates were in ``VERB_UNDECIDABLE`` until
#: an agent existed that could actually drive them. That entry said 「矢印
#: そのものが動詞なので抜く相手が無い」, which was the wrong half of the truth:
#: there was plenty to withhold, and what was missing was competence on the
#: other side.
VERB_TEMPLATES: dict[str, dict[str, str]] = {
    "fishing": {"verb": "キャストする", "kind": "space", "measure": "score"},
    "kaiju": {"verb": "撃つ", "kind": "space", "measure": "cycles"},
    "shooter": {"verb": "撃つ", "kind": "space", "measure": "best"},
    "duel": {"verb": "斬る", "kind": "space", "measure": "alive"},
    "racing": {"verb": "ハンドルを切る", "kind": "steer", "measure": "dist"},
    "catch": {"verb": "かごを動かす", "kind": "steer", "measure": "score"},
    "marble": {"verb": "舵を切る", "kind": "steer", "measure": "score"},
    "puzzle": {"verb": "組を消す", "kind": "pop", "measure": "score"},
}

#: Why the rest cannot be decided by this agent. A limit of the measurement,
#: not a finding about the template - §34 事実 2 is the whole reason this
#: dictionary exists rather than three confident zeroes.
#:
#: Both need an agent that can finish something: a dungeon, a course. The
#: agents above are greedy one-liners over facts the page already publishes,
#: and there is no equivalent for 「walk the dungeon」 or 「cross the gaps」.
#:
#: C-1890 removed the third. ``puzzle`` sat here with the reason 「盤を解ける
#: エージェントがまだ無い」 until C-1889's work on the board showed the page
#: publishes ``group(x, y)`` - so a greedy agent that takes the largest group
#: is a few lines, exactly as ``roadAt`` made racing decidable. A reason that
#: names what is missing is a reason somebody can remove, and this one was.
VERB_UNDECIDABLE: dict[str, str] = {
    "adventure": "鍵を取って宝箱まで辿り着けるエージェントがまだ無い——歩き回るだけでは、負けたのが動詞のせいか下手のせいか分けられない",
    "platformer": "旗まで跳んで渡れるエージェントがまだ無い——足場の切れ目を見て跳ぶ走者でも実測 x202/1997・落下 46 回で、跳ばない走者の x204 と差が付かなかった（2026-09-16）",
}

_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)

_HARNESS = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function frame(){ if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }
function down(k){ (handlers.keydown || []).forEach(fn => fn(probeKey(k))) }
function up(k){ (handlers.keyup || []).forEach(fn => fn(probeKey(k))) }
function tap(k){ down(k); up(k) }
const USE_VERB = USE_VERB_TOKEN;
const KIND = KIND_TOKEN;
tap(' ');
let held = null;
/* Where a competent driver would be heading this frame, asked of the page
   rather than worked out here. racing publishes `roadAt(d)` and its own
   notes say the probe may ask it, so the course's two sines are not copied
   into this file (C-1342's shared-constant rule, C-1640's 「do not read the
   ledger」). catch has `items` and the basket's own `shown`; marble has
   `things` and `ball`. Greedy, not perfect - §34 事実 2 asks for competent,
   and competent is what separates the two runs. */
function steerWant(){
  try {
    if (typeof items !== 'undefined' && typeof shown !== 'undefined') {
      let low = null;
      for (const it of items) { if (!low || it.y > low.y) low = it }
      if (!low) return null;
      return (low.x > shown + 0.01) ? 'ArrowRight'
           : (low.x < shown - 0.01) ? 'ArrowLeft' : null;
    }
    if (typeof roadAt === 'function' && typeof car !== 'undefined') {
      const mid = roadAt(dist);
      return (car.x < mid - 4) ? 'ArrowRight'
           : (car.x > mid + 4) ? 'ArrowLeft' : null;
    }
    if (typeof things !== 'undefined' && typeof ball !== 'undefined') {
      let next = null;
      for (const o of things) {
        if (o.kind !== 'gate' || o.z <= ball.z) continue;
        if (!next || o.z < next.z) next = o }
      if (!next) return null;
      return (next.x > ball.x + 3) ? 'ArrowRight'
           : (next.x < ball.x - 3) ? 'ArrowLeft' : null;
    }
  } catch (e) {}
  return null;
}
for (let i = 0; i < FRAMES_TOKEN; i++) {
  if (KIND === 'space') {
    /* The SAME agent in both runs, so the only difference is the action
       key. It paces left and right rather than parking, because a parked
       agent is a different (and worse) agent, not a crippled one. */
    const k = (Math.floor(i / 40) % 2) ? 'ArrowRight' : 'ArrowLeft';
    if (i % 40 === 0) down(k);
    if (i % 40 === 39) up(k);
    if (USE_VERB && i % 12 === 0) tap(' ');
  } else if (KIND === 'pop') {
    /* The board's verb is taking a group. Competence comes from the page's
       own group(x, y) - the same place racing's roadAt came from - so the
       judge carries no idea of its own about what a good move is. The
       crippled run walks the cursor instead, which is the closest thing to
       「playing without the verb」 a board game has. */
    if (USE_VERB) {
      let best = null;
      try {
        for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
          if (grid[y][x] < 0) continue;
          const g = group(x, y);
          if (g.length >= 2 && (!best || g.length > best.n))
            best = { x: x, y: y, n: g.length } }
      } catch (e) {}
      if (best) { cur.x = best.x; cur.y = best.y; tap(' ') }
    } else {
      const k = (Math.floor(i / 7) % 2) ? 'ArrowRight' : 'ArrowDown';
      if (i % 7 === 0) down(k);
      if (i % 7 === 6) up(k);
    }
  } else {
    /* The arrows ARE the verb here, so the crippled run presses nothing. */
    const want = USE_VERB ? steerWant() : null;
    if (want !== held) { if (held) up(held); if (want) down(want); held = want }
  }
  frame();
}
if (held) up(held);
/* Underscored, because the page declares `score` and `state` itself with
   `let` at the top level and a second declaration in the same scope is a
   SyntaxError - which the probe reports as 「unavailable」, i.e. as the
   template's fault. */
let _vScore = null, _vState = null, _vCycles = null, _vBest = null;
try { _vScore = (typeof score !== 'undefined') ? score : null } catch (e) {}
try { _vState = (typeof state !== 'undefined') ? state : null } catch (e) {}
try { if (typeof bossFacts === 'function') _vCycles = bossFacts().cycles } catch (e) {}
try { if (typeof roundFacts === 'function') _vBest = roundFacts().best } catch (e) {}
let _vDist = null;
try { if (typeof raceFacts === 'function') _vDist = raceFacts().dist } catch (e) {}
console.log(JSON.stringify({ score: _vScore, state: _vState, cycles: _vCycles,
                             best: _vBest, dist: _vDist }));
"""


@dataclass(frozen=True)
class VerbResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    shown: int = 0
    decided: tuple[str, ...] = ()


def _run(job: tuple[str, str, bool]) -> tuple[str, bool, dict | None, str]:
    template, script, use_verb = job
    source = (
        _HARNESS.replace("SCRIPT_PLACEHOLDER", script)
        .replace("USE_VERB_TOKEN", "true" if use_verb else "false")
        .replace("KIND_TOKEN", json.dumps(VERB_TEMPLATES[template]["kind"]))
        .replace("FRAMES_TOKEN", str(FRAMES))
    )
    try:
        run = subprocess.run(
            ["node", "-"], input=source, capture_output=True, text=True, timeout=240
        )
        if run.returncode != 0:
            return template, use_verb, None, run.stderr.strip()[:60]
        return template, use_verb, json.loads(run.stdout.strip().splitlines()[-1]), ""
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return template, use_verb, None, type(exc).__name__


def _reading(template: str, seen: dict) -> float:
    """One number per template, in the terms that template plays in."""

    if template == "fishing":
        return float(seen.get("score") or 0)
    if template == "kaiju":
        return float(seen.get("cycles") or 0)
    if template == "shooter":
        return float(seen.get("best") or 0)
    if template == "duel":
        # The duel ends when somebody goes down; a player who never swings is
        # the one who goes down, so still being in play IS the progress.
        return 1.0 if seen.get("state") == "play" else 0.0
    if template == "racing":
        # Distance, not laps: a lap is a step function and two runs can sit
        # either side of one by luck. Distance separates every frame.
        return float(seen.get("dist") or 0)
    if template in ("catch", "marble", "puzzle"):
        return float(seen.get("score") or 0)
    return 0.0


def evaluate_requires_its_own_verb() -> VerbResult:
    checks = 0
    failures: list[str] = []
    shown: list[str] = []

    jobs: list[tuple[str, str, bool]] = []
    for template in sorted(VERB_TEMPLATES):
        page = generate_game("ゲームを作って", template=template).html
        script = _SCRIPT.search(page)
        if script is None:
            failures.append(f"{template}: no script")
            continue
        jobs.append((template, script.group(1), True))
        jobs.append((template, script.group(1), False))

    # Eight subprocesses waiting on a child hold no GIL; spawning them in a
    # plain loop is what cost metrics_node_work_is_bundled 1.4 points in
    # C-1857.
    with ThreadPoolExecutor(max_workers=4) as pool:
        done = list(pool.map(_run, jobs))

    got: dict[tuple[str, bool], dict | None] = {}
    for template, use_verb, seen, why in done:
        got[(template, use_verb)] = seen
        if seen is None:
            failures.append(f"{template}: probe unavailable ({why})")

    for template in sorted(VERB_TEMPLATES):
        with_verb = got.get((template, True))
        without = got.get((template, False))
        if with_verb is None or without is None:
            continue
        here, gone = _reading(template, with_verb), _reading(template, without)
        # Direction one: the verb gets the agent somewhere at all. Without
        # this the whole judge is satisfied by a game nobody can play.
        if here > 0:
            checks += 1
        else:
            failures.append(f"{template}: the verb got nowhere ({here})")
        # Direction two: taking it away costs.
        if gone < here:
            checks += 1
            shown.append(template)
        else:
            failures.append(
                f"{template}: the same without the verb ({here} vs {gone})"
            )

    # The sample says what it covers. Ten templates, four decided, six named
    # with a reason - and a template in neither list is a template nobody
    # thought about, which is the gap this shape exists to make visible.
    both = set(VERB_TEMPLATES) | set(VERB_UNDECIDABLE)
    missing = sorted(set(TEMPLATES) - both)
    doubled = sorted(set(VERB_TEMPLATES) & set(VERB_UNDECIDABLE))
    stray = sorted(both - set(TEMPLATES))
    for key in missing:
        failures.append(f"{key}: neither decided nor explained")
    for key in doubled:
        failures.append(f"{key}: both decided and explained")
    for key in stray:
        failures.append(f"{key}: listed but not a template")
    for key, why in sorted(VERB_UNDECIDABLE.items()):
        if len(why.strip()) > 20:
            checks += 1
        else:
            failures.append(f"{key}: undecidable with no reason written")

    return VerbResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
        shown=len(shown),
        decided=tuple(sorted(shown)),
    )


__all__ = [
    "FRAMES",
    "VERB_TEMPLATES",
    "VERB_UNDECIDABLE",
    "VerbResult",
    "evaluate_requires_its_own_verb",
]
