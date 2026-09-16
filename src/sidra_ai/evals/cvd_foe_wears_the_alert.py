"""Is the foe the one wearing the alert colour?

`creation_cvd_info_pair` separates a theme's `accent` from its `alert`
through three colour-vision matrices, and C-1891 added the half that asks
whether those two tokens are painted at all. Its own docstring then said
what it still could not say: that the FOE is the alert one. The evidence
was blunt - recolouring all three of shooter's `MAGENTA_TOKEN` calls to
the hero's colour moved no number, because the HUD, the result band and
the juice preambles paint alert too.

That remaining half is the point of the pair. What a colour-vision judge
protects is telling the hero from the thing that can kill you; "both
colours appear somewhere on the page" is a weaker promise than the one
`creation_cvd_info_pair` is named for.

Measuring it means attributing paint to entities, and a recorder that
watches only `fillRect` and `arc` cannot: these templates draw their
sprites as paths. This one follows the pen - `beginPath`, `moveTo`,
`lineTo`, `arc`, `rect` - and books a mark at `fill()` or `stroke()` with
the colour and the box the path covered. The page's own coordinates say
where the hero and the foe are, so the question becomes: of the marks
covering the foe, is one the alert token, and is the hero's body not?

Both directions are asked. A page that painted everything alert would
pass "the foe is alert" and fail "the hero is not", and a judge that only
asked the first would call it correct.

Three tables, not two. A page with no foe is excused; a page with a foe
this probe cannot yet stand in front of is named as such. adventure is in
the second group - its roamers are drawn with `MAGENTA_TOKEN` and live in
the rooms past the entrance, so calling it foe-less to keep the sheet
clean would be the false excuse C-1896 added a check to catch.
"""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sidra_ai.creation.duel import KEY_EVENT_JS

#: Templates with a hero and a foe that can both be pointed at, the
#: request that makes each, and the page's own expressions for where the
#: two stand. `drive` is what has to happen before a foe exists.
FOE_PAGES: dict[str, dict[str, str]] = {
    "shooter": {
        "request": "シューティングゲームを作って",
        "drive": "press(' '); lift(' ');",
        "each": "",
        "ready": "typeof foes !== 'undefined' && foes.length > 0",
        "hero": "[ship.x, ship.y]",
        "foe": "[foes[0].x, foes[0].y]",
    },
    "duel": {
        "request": "ビームで撃ち合うゲームを作って",
        "drive": "press(' '); lift(' ');",
        "each": "",
        "ready": "typeof e !== 'undefined' && state === 'play'",
        "hero": "[p.x, LANES[p.lane]]",
        "foe": "[e.x, LANES[e.lane]]",
    },
}

#: Templates with no foe to point at, and why. Written down so leaving a
#: page out is a decision rather than an omission.
NO_FOE: dict[str, str] = {
    "platformer": "危険が「物」ではなく足場の切れ目なので、敵の位置というものが無い（C-1891 の理由と同じ）",
    "marble": "奥行きを明るさで描く型で、障害は色ではなく形と影で示す",
    "racing": "追い越す相手ではなくコースそのものが相手——障害物は道の外側",
    "puzzle": "盤上に敵が居らず、相手は手詰まりという状態",
    "catch": "落ちてくる物を受ける型で、敵役が居ない",
    "fishing": "釣り上げる相手は獲物であって脅威ではない",
    "kaiju": "巨獣は部分描写で全身を見せない（§6 観察 1）ので、"
             "「敵の位置」が 1 点に定まらない——脚と頭が別々に動く",
}

#: Templates that DO have a foe but that this probe cannot yet stand in
#: front of, and what stops it. Kept apart from NO_FOE on purpose: saying
#: 「この型に敵は居ない」 about a page whose roamers are drawn with
#: MAGENTA_TOKEN would be a false excuse, and C-1896 added a check
#: precisely to stop a page being excused for something it does not have.
#: A gap named as a gap can be taken; a gap dressed as a design decision
#: cannot.
NOT_YET_REACHED: dict[str, str] = {
    "adventure": "roamer は部屋ごとに居て、入口の部屋には居ない——"
                 "主役を歩かせて同じ部屋に立たせる探針が要る（矢印を押す程度では届かなかった）。"
                 "**敵は `sprite('enemy',…,'MAGENTA_TOKEN')` で描かれている**ので、"
                 "「敵が居ない」ではなく「まだ測れていない」",
}

#: How close a mark's box has to come to the entity's own coordinates to
#: count as covering it.
REACH = 14.0

_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get:(t,k)=>(k===Symbol.toPrimitive?()=>0:nothing), apply:()=>nothing, set:()=>true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let NOW = 0;
globalThis.performance = { now: () => NOW };
globalThis.addEventListener = (type, fn) => { (handlers[type]=handlers[type]||[]).push(fn) };
/* An Image that reports itself unloaded, which is what a page with no
   asset actually has. The usual `nothing` proxy answers every property
   truthily, so `sprite()` took its drawImage branch and the roamer was
   never painted through fillRect - adventure's foe came back as the floor
   tile it stands on. */
globalThis.Image = function(){ return { complete:false, naturalWidth:0,
  addEventListener:function(){}, set src(v){}, get src(){ return '' } } };
/* Follow the pen, and book a mark when the page fills or strokes: these
   sprites are paths, and a recorder watching only fillRect/arc sees none
   of them (C-1903's hand-off note, written after exactly that failure). */
let MARKS = [], FILL = '', STROKE = '', PATH = null;
function _pt(x,y){ if(typeof x!=='number'||typeof y!=='number') return;
  if(!PATH) PATH={x0:x,y0:y,x1:x,y1:y};
  else { PATH.x0=Math.min(PATH.x0,x); PATH.y0=Math.min(PATH.y0,y);
         PATH.x1=Math.max(PATH.x1,x); PATH.y1=Math.max(PATH.y1,y) } }
function _book(colour){ if(!PATH) return;
  MARKS.push({c:String(colour), x:(PATH.x0+PATH.x1)/2, y:(PATH.y0+PATH.y1)/2,
              w:PATH.x1-PATH.x0, h:PATH.y1-PATH.y0}) }
const rec = new Proxy(function(){}, {
  get:(t,k)=>{
    if(k==='fillStyle') return FILL;
    if(k==='strokeStyle') return STROKE;
    if(k==='beginPath') return ()=>{ PATH=null };
    if(k==='moveTo'||k==='lineTo') return (x,y)=>_pt(x,y);
    if(k==='arc') return (x,y,r)=>{ _pt(x-r,y-r); _pt(x+r,y+r) };
    if(k==='rect') return (x,y,w,h)=>{ _pt(x,y); _pt(x+w,y+h) };
    if(k==='fill') return ()=>_book(FILL);
    if(k==='stroke') return ()=>_book(STROKE);
    if(k==='fillRect') return (x,y,w,h)=>{ MARKS.push({c:String(FILL),x:x+w/2,y:y+h/2,w:w,h:h}) };
    if(k===Symbol.toPrimitive) return ()=>0; return nothing },
  set:(t,k,v)=>{ if(k==='fillStyle') FILL=String(v);
                 if(k==='strokeStyle') STROKE=String(v); return true },
  apply:()=>nothing });
globalThis.document = { getElementById: () => ({
  width:720, height:320, style:{}, addEventListener:()=>{},
  getBoundingClientRect:()=>({left:0,top:0,width:720,height:320}),
  getContext: () => rec }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function frame(){ if(!queued) return false; const fn=queued; queued=null; MARKS=[]; NOW+=16.667; fn(NOW); return true }
function press(k){ (handlers.keydown||[]).forEach(f=>f(probeKey(k||' '))) }
function lift(k){ (handlers.keyup||[]).forEach(f=>f(probeKey(k||' '))) }
DRIVE_PLACEHOLDER
const REACH = REACH_PLACEHOLDER;
/* Every sprite-sized colour laid over a point, not one chosen from them.
   Picking "the biggest mark" read adventure's floor tile instead of the
   roamer standing on it, and picking "the last mark" read the dark detail
   on shooter's hull instead of the hull - both times a rule about which
   mark counts, when the question is only whether the alert token is among
   them. */
function coats(tx, ty){
  return MARKS.filter(m=>Math.max(m.w,m.h) < 60
    && Math.abs(m.x-tx) < REACH && Math.abs(m.y-ty) < REACH).map(m=>m.c);
}
let out = {hero:null, foe:null, frames:0};
for (let i=0;i<1200;i++){
  PER_FRAME_PLACEHOLDER
  if(!frame()) break;
  out.frames = i + 1;
  let ready = false;
  try { ready = !!(READY_PLACEHOLDER) } catch (err) { ready = false }
  if(!ready) continue;
  let hp = null, fp = null;
  try { hp = HERO_PLACEHOLDER; fp = FOE_PLACEHOLDER } catch (err) { continue }
  const hc = coats(hp[0], hp[1]), fc = coats(fp[0], fp[1]);
  if (hc.length && fc.length) { out.hero = hc; out.foe = fc; break }
}
console.log(JSON.stringify(out));
"""


@dataclass(frozen=True)
class FoeAlertResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def build_probe(script: str, *, spec: dict[str, str]) -> str:
    return (
        _PROBE.replace("SCRIPT_PLACEHOLDER", script)
        .replace("DRIVE_PLACEHOLDER", spec["drive"])
        .replace("PER_FRAME_PLACEHOLDER", spec.get("each", ""))
        .replace("READY_PLACEHOLDER", spec["ready"])
        .replace("HERO_PLACEHOLDER", spec["hero"])
        .replace("FOE_PLACEHOLDER", spec["foe"])
        .replace("REACH_PLACEHOLDER", repr(REACH))
    )


def _run(job: tuple[str, str, dict]) -> tuple[str, dict | str]:
    template, script, spec = job
    try:
        run = subprocess.run(
            ["node", "-"], input=build_probe(script, spec=spec),
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


def evaluate_cvd_foe_wears_the_alert() -> FoeAlertResult:
    from sidra_ai.creation.games import TEMPLATES, generate_game
    from sidra_ai.creation.themes import DEFAULT_THEME

    failures: list[str] = []
    jobs: list[tuple[str, str, dict]] = []
    for template, spec in sorted(FOE_PAGES.items()):
        html = generate_game(spec["request"]).html
        script = re.search(r"<script>(.*?)</script>", html, re.S)
        if script is None:
            failures.append(f"{template}: no script on the page")
            continue
        jobs.append((template, script.group(1), spec))

    # The tokens as the default theme resolves them, so the comparison is
    # against what the page was actually given rather than a name.
    palette = DEFAULT_THEME.tokens
    alert = str(palette.get("alert", "")).lower()

    checks = 0
    readings: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for template, out in pool.map(_run, jobs):
            if isinstance(out, str):
                failures.append(f"{template}: {out}")
                continue
            hero = [str(c).lower() for c in (out.get("hero") or [])]
            foe = [str(c).lower() for c in (out.get("foe") or [])]
            if not hero or not foe:
                failures.append(
                    f"{template}: no mark was found on the "
                    + ("foe" if hero else "hero")
                )
                continue
            if alert not in foe:
                failures.append(
                    f"{template}: nothing on the foe is the alert {alert} "
                    f"(found {'・'.join(sorted(set(foe)))})"
                )
            else:
                checks += 1
            if alert in hero:
                failures.append(f"{template}: the hero wears the alert colour too")
            else:
                checks += 1
            readings.append(
                f"{template}=敵 {'・'.join(sorted(set(foe)))}／主役 {'・'.join(sorted(set(hero)))}"
            )

    # Every template sits in exactly one of the three tables: measured,
    # genuinely foe-less, or named as not yet reached.
    tables = (set(FOE_PAGES), set(NO_FOE), set(NOT_YET_REACHED))
    named = tables[0] | tables[1] | tables[2]
    for template in sorted(set(TEMPLATES) - named):
        failures.append(f"{template} is in none of the three tables")
    for i, a in enumerate(tables):
        for b in tables[i + 1:]:
            for template in sorted(a & b):
                failures.append(f"{template} is in two tables at once")
    if named == set(TEMPLATES) and len(tables[0] | tables[1] | tables[2]) == sum(
        len(t) for t in tables
    ):
        checks += 1

    return FoeAlertResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
