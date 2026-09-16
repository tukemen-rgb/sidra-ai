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

#: The templates whose own action is a key that can be withheld, and what
#: 「got somewhere」 means for each. ``measure`` is read off the page after the
#: run; ``progress`` is what the agent WITH the verb must beat.
VERB_TEMPLATES: dict[str, dict[str, str]] = {
    "fishing": {"verb": "キャストする", "measure": "score"},
    "kaiju": {"verb": "撃つ", "measure": "cycles"},
    "shooter": {"verb": "撃つ", "measure": "best"},
    "duel": {"verb": "斬る", "measure": "alive"},
}

#: Why the rest cannot be decided by this agent. A limit of the measurement,
#: not a finding about the template - §34 事実 2 is the whole reason this
#: dictionary exists rather than six confident zeroes.
VERB_UNDECIDABLE: dict[str, str] = {
    "racing": "矢印そのものが動詞（ハンドル）なので、SPACE を抜いても何も抜けていない",
    "catch": "矢印そのものが動詞（かごを動かす）なので、抜く相手が無い",
    "marble": "矢印そのものが動詞（舵）なので、抜く相手が無い",
    "adventure": "歩き回るだけでは 1 ラウンドで宝箱に届かない——負けたのが動詞のせいか下手のせいか分けられない",
    "platformer": "歩き回るだけでは旗に届かない——負けたのが動詞のせいか下手のせいか分けられない",
    "puzzle": "動詞ありと無しで点が並ぶが、盤を解いているのではなく触れているだけで、歩き回るだけのエージェントには分けられない",
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
tap(' ');
for (let i = 0; i < FRAMES_TOKEN; i++) {
  /* The SAME agent in both runs, so the only difference is the verb. It
     paces left and right rather than parking, because a parked agent is a
     different (and worse) agent, not a crippled one. */
  const k = (Math.floor(i / 40) % 2) ? 'ArrowRight' : 'ArrowLeft';
  if (i % 40 === 0) down(k);
  if (i % 40 === 39) up(k);
  if (USE_VERB && i % 12 === 0) tap(' ');
  frame();
}
/* Underscored, because the page declares `score` and `state` itself with
   `let` at the top level and a second declaration in the same scope is a
   SyntaxError - which the probe reports as 「unavailable」, i.e. as the
   template's fault. */
let _vScore = null, _vState = null, _vCycles = null, _vBest = null;
try { _vScore = (typeof score !== 'undefined') ? score : null } catch (e) {}
try { _vState = (typeof state !== 'undefined') ? state : null } catch (e) {}
try { if (typeof bossFacts === 'function') _vCycles = bossFacts().cycles } catch (e) {}
try { if (typeof roundFacts === 'function') _vBest = roundFacts().best } catch (e) {}
console.log(JSON.stringify({ score: _vScore, state: _vState,
                             cycles: _vCycles, best: _vBest }));
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
