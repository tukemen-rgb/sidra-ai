"""When a run ends, is the result said to someone who cannot see it?

C-1907 gave the canvas a sentence naming what it is. This is the next
thing the same reader still could not get: the result. 「撃墜 12 機・得点
340。」 is drawn on the canvas and nowhere else, so a screen reader has no
way to learn that the run even finished.

WCAG 4.1.3 puts it plainly - status messages must be 「programmatically
determined through role or properties such that they can be presented to
the user by assistive technologies without receiving focus」, and the
criterion's own examples are exactly this kind of message: the result of
an action. The generated pages had no `aria-live` and no `role="status"`
anywhere at all.

The end states come from `end_text_is_centred`, so the two judges cannot
disagree about how a page reaches its result screen: one checks the words
are centred, this one checks they are also said.

Both endings are driven: the one a template draws for itself, and the
one `round.py` draws when the clock runs out. They are different code
paths - the rAF wrapper returns before the template's own frame once the
round is done - and the second is the only ending catch and fishing have.

Four directions:

  (a) the page carries a polite live region at all;
  (b) once the run ends, that region holds something;
  (c) what it holds is what the canvas says - the same result, not a
      generic 「おわり」;
  (d) it is written ONCE. draw() runs every frame, and a live region
      rewritten sixty times a second is sixty announcements; a judge that
      only checked "not empty" would grade that as a pass.
"""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sidra_ai.creation.duel import KEY_EVENT_JS
from sidra_ai.evals.end_text_is_centred import END_STATES, NO_END_SCREEN

#: How many frames to run after the end state is set, to see whether the
#: page keeps re-announcing.
FRAMES_AFTER_END = 60

#: The other ending. `round.py` draws 「ここまで」 when the clock runs out,
#: and the rAF wrapper returns before the template's own frame, so this is
#: a different code path from the eight endings above - not a variant of
#: them. For catch and fishing it is the ONLY ending they have, which is
#: why C-1896 recorded them as drawing no end screen of their own; C-1908
#: then wired the eight and left this one silent (C-1910).
ROUND_END_PAGES: dict[str, tuple[str, str]] = {
    "catch": ("落ちてくるものを受け止めるゲームを作って", "ROUND_DONE=true"),
    "fishing": ("魚釣りゲームを作って", "ROUND_DONE=true"),
}

_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get:(t,k)=>(k===Symbol.toPrimitive?()=>0:nothing), apply:()=>nothing, set:()=>true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let NOW = 0;
globalThis.performance = { now: () => NOW };
globalThis.addEventListener = (type, fn) => { (handlers[type]=handlers[type]||[]).push(fn) };
globalThis.Image = function(){ return { complete:false, naturalWidth:0,
  addEventListener:function(){}, set src(v){}, get src(){ return '' } } };
/* Elements the page asks for by id, so what it writes can be read back.
   Every write to textContent is counted: saying it twice is its own
   defect. */
const ELEMENTS = {};
let SAID_WRITES = 0;
function element(id){
  if (ELEMENTS[id]) return ELEMENTS[id];
  let text = '';
  const el = { id: id, style: {}, addEventListener: function(){},
    width: 720, height: 320,
    getBoundingClientRect: function(){ return {left:0,top:0,width:720,height:320} },
    getContext: function(){ return rec },
    get textContent(){ return text },
    set textContent(v){ if (id === 'said') SAID_WRITES++; text = String(v) } };
  ELEMENTS[id] = el; return el;
}
/* The words the canvas draws, with the size they were drawn at, so what
   is SAID can be held against what is SHOWN. */
let DRAWN = [], FONT = '';
const rec = new Proxy(function(){}, {
  get:(t,k)=>{
    if(k==='font') return FONT;
    if(k==='fillText') return (text)=>{ const m=/^\\s*([0-9.]+)px/.exec(FONT);
      DRAWN.push({t:String(text), px: m?parseFloat(m[1]):0}) };
    if(k===Symbol.toPrimitive) return ()=>0; return nothing },
  set:(t,k,v)=>{ if(k==='font') FONT=String(v); return true }, apply:()=>nothing });
globalThis.document = { getElementById: element, querySelector: () => element('stage'),
  createElement: () => element('made') };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function frame(){ if(!queued) return false; const fn=queued; queued=null; NOW+=16.667; fn(NOW); return true }
function press(k){ (handlers.keydown||[]).forEach(f=>f(probeKey(k||' '))) }
function lift(k){ (handlers.keyup||[]).forEach(f=>f(probeKey(k||' '))) }
press(' '); lift(' ');
for (let i=0;i<5;i++) frame();
try { STATE_PLACEHOLDER } catch (err) {}
SAID_WRITES = 0;
DRAWN = [];
for (let i=0;i<FRAMES_PLACEHOLDER;i++) frame();
/* The headline of the end screen: the biggest type drawn while it was up. */
let head = '';
let headPx = 0;
for (const d of DRAWN) { if (d.px > headPx && d.t.trim()) { headPx = d.px; head = d.t } }
console.log(JSON.stringify({ said: element('said').textContent,
  writes: SAID_WRITES, drawn: head }));
"""


@dataclass(frozen=True)
class AnnouncedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def build_probe(script: str, *, state: str) -> str:
    return (
        _PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("STATE_PLACEHOLDER", state)
        .replace("FRAMES_PLACEHOLDER", str(FRAMES_AFTER_END))
    )


def _run(job: tuple[str, str, str]) -> tuple[str, dict | str]:
    template, script, state = job
    try:
        run = subprocess.run(
            ["node", "-"], input=build_probe(script, state=state),
            capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return template, f"probe unavailable ({type(exc).__name__})"
    if run.returncode != 0:
        return template, run.stderr.strip()[:80] or "node failed"
    try:
        return template, json.loads(run.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return template, "probe printed nothing readable"


def evaluate_result_is_announced() -> AnnouncedResult:
    from sidra_ai.creation.games import TEMPLATES, generate_game

    failures: list[str] = []
    jobs: list[tuple[str, str, str]] = []
    everywhere = dict(END_STATES)
    everywhere.update(ROUND_END_PAGES)
    for template, (request, state) in sorted(everywhere.items()):
        html = generate_game(request).html
        # (a) the region itself, read from the page that ships
        if 'role="status"' not in html or 'aria-live="polite"' not in html:
            failures.append(f"{template}: the page carries no polite live region")
            continue
        script = re.search(r"<script>(.*?)</script>", html, re.S)
        if script is None:
            failures.append(f"{template}: no script on the page")
            continue
        jobs.append((template, script.group(1), state))

    readings: list[str] = []
    checks = len(jobs)  # each page that got this far has its region
    with ThreadPoolExecutor(max_workers=4) as pool:
        for template, out in pool.map(_run, jobs):
            if isinstance(out, str):
                failures.append(f"{template}: {out}")
                continue
            said = str(out.get("said") or "").strip()
            writes = int(out.get("writes") or 0)
            # (b) something was said
            if not said:
                failures.append(f"{template}: the run ended and nothing was said")
                continue
            checks += 1
            # (d) and said once, not once a frame
            if writes > 1:
                failures.append(
                    f"{template}: the result was written {writes} times in "
                    f"{FRAMES_AFTER_END} frames"
                )
            else:
                checks += 1
            # (c) and what was said is what was shown. Compared without
            # the sentence-ending 「。」 an announcement may add, and in
            # both directions, because a template may draw a headline the
            # announcement expands on (or the reverse).
            drawn = str(out.get("drawn") or "").strip()
            bare = lambda x: x.replace("。", "").replace(" ", "").strip()
            if not drawn:
                failures.append(f"{template}: the end screen drew no headline to compare")
            elif not (bare(drawn) in bare(said) or bare(said) in bare(drawn)):
                failures.append(
                    f"{template}: the canvas shows 「{drawn}」 and the page says 「{said}」"
                )
            else:
                checks += 1
            readings.append(f"{template}=「{said[:26]}…」" if len(said) > 26 else f"{template}=「{said}」")

    # Every template ends somehow, and every ending is driven here: the
    # eight a template draws for itself, and the clock's for the rest.
    # NO_END_SCREEN is the centring judge's table - a page with no end
    # screen OF ITS OWN still ends, and still has to say so.
    named = set(END_STATES) | set(ROUND_END_PAGES)
    for template in sorted(set(TEMPLATES) - named):
        failures.append(f"{template} has no ending driven here")
    for template in sorted(set(END_STATES) & set(ROUND_END_PAGES)):
        failures.append(f"{template} is driven through two endings at once")
    if named == set(TEMPLATES) and not (set(END_STATES) & set(ROUND_END_PAGES)):
        checks += 1
    for template in sorted(set(NO_END_SCREEN) - set(ROUND_END_PAGES)):
        failures.append(
            f"{template} draws no end screen of its own and is not driven "
            "through the clock's ending either"
        )

    return AnnouncedResult(
        passed=not failures and len(readings) == len(END_STATES) + len(ROUND_END_PAGES),
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
