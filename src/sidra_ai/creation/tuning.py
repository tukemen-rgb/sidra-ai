"""A tuning panel shipped inside the generated page.

The knowledge base (``docs/research/game-design-notes.md`` §9 学び (4))
records the same complaint about every generator on the market: when the
model gets it *nearly* right, the person is stuck. They can ask again and
get a different game, or they can give up. What decides satisfaction is
whether there is a way to finish the job by hand.

C-1112 gave the first half of that - 「もっと難しくして」 edits the
recorded parameters and rebuilds. This is the other half, and it is
deliberately the half that needs nobody: the page carries its own form.
Pull open 「調整」 at the bottom of the artifact, move a slider, and the
game runs with the new number. No request, no backend, no rebuild - the
HTML file on disk is untouched, and the values live in that browser's
``localStorage`` under one key per template.

Three properties are load-bearing, and each is measured rather than
asserted (``creation_param_panel`` in ``scripts/product_metrics.py``):

* **The envelope is the designed one.** A slider's ``min``/``max`` come
  from the template's own ``_DIFFICULTY`` row - its easy and hard values,
  nothing wider. A person can make the game any difficulty the author
  shipped and cannot make it unplayable, and an axis the template reads
  with ``%`` (a frame interval) keeps integer steps.
* **Nothing leaves the machine.** The panel reads and writes
  ``localStorage`` and calls ``location.reload()``. There is no ``fetch``
  and no URL in this module, which is the same trust boundary the
  artifact and the index already sit inside.
* **Every template gets it for free.** The panel is a preamble, like the
  pad and the juice, and the two numbers it drives are the two tokens
  every template already substitutes (``SPEED_TOKEN``/``BAND_TOKEN``).
  A template written tomorrow is adjustable the day it is written.

Colour is the third axis §9 names, and it is applied the same way: the
accent every template paints with is substituted as the identifier
``TUNE_ACCENT`` instead of a hex literal, so one stored value repaints
all thirty of its uses at load.
"""

from __future__ import annotations

import json

#: The one difficulty ladder, in climbing order - the same three names
#: ``_DIFFICULTY`` in games.py is keyed by and ``revise.py`` walks. Named
#: here rather than imported so this module stays importable from games.py.
LADDER: tuple[str, ...] = ("easy", "normal", "hard")

#: What the two shared tokens *mean* for each template. The contract is
#: uniform (``SPEED_TOKEN``, ``BAND_TOKEN``); the meaning is not, and a
#: slider labelled "speed" on the puzzle board - where the axis is how many
#: colours are in play - would be a lie a person acts on.
AXIS_LABELS: dict[str, tuple[str, str]] = {
    "fishing": ("マーカーの速さ", "当たり判定の幅"),
    "catch": ("落ちてくる間隔", "受け皿の幅"),
    "adventure": ("敵の速さ", "敵の数"),
    "duel": ("CPU の溜め速度", "CPU の判断間隔"),
    "shooter": ("降下の速さ", "湧きの間隔"),
    "puzzle": ("色の数", "盤の幅"),
    "kaiju": ("外殻が開く速さ", "脚の耐久"),
    "racing": ("基本ペース", "障害物の最小間隔"),
    "platformer": ("足場の間隔", "足場の数"),
}

#: Fallback for a template nobody has written a label for yet. Vague, but
#: honest - and the schema still carries the real numbers.
_DEFAULT_LABELS = ("速さ", "広さ")


def _axis(values: tuple[float, ...]) -> dict:
    """Range and step for one axis, from the three difficulties it spans."""

    low, high = min(values), max(values)
    integral = all(float(v).is_integer() for v in values)
    if integral:
        return {"min": int(low), "max": int(high), "step": 1, "integer": True}
    # Twenty stops across the shipped span: fine enough to feel like a dial,
    # coarse enough that the number in the box stays readable.
    step = round((high - low) / 20, 6) or 0.001
    return {"min": low, "max": high, "step": step, "integer": False}


def panel_schema(template: str, ladder: dict[str, tuple[float, float]], *, difficulty: str, accent: str) -> dict:
    """The JSON schema of one page's adjustable parameters.

    ``ladder`` is the template's row out of ``games._DIFFICULTY``: the
    three ``(speed, band)`` pairs the author shipped. Passed in rather than
    imported so this module does not import games.py, which imports it.
    """

    speeds = tuple(pair[0] for pair in ladder.values())
    bands = tuple(pair[1] for pair in ladder.values())
    names = AXIS_LABELS.get(template, _DEFAULT_LABELS)
    chosen = difficulty if difficulty in ladder else "normal"
    speed, band = ladder[chosen]
    return {
        "template": template,
        "fields": [
            {
                "key": "difficulty",
                "label": "難度",
                "type": "choice",
                "default": chosen,
                "choices": [name for name in LADDER if name in ladder],
                # Picking a preset writes both axes, so the two fine
                # sliders and the preset can never disagree about what
                # "hard" is - they are the same table.
                "presets": {
                    name: {"speed": pair[0], "band": pair[1]}
                    for name, pair in ladder.items()
                },
            },
            {"key": "speed", "label": names[0], "type": "number", "default": speed, **_axis(speeds)},
            {"key": "band", "label": names[1], "type": "number", "default": band, **_axis(bands)},
            {"key": "accent", "label": "差し色", "type": "colour", "default": accent},
            # C-1107. Off by default: the request-derived seed is what makes
            # a generated game *that person's* game, and a revision rebuilt
            # from the same request expects the same world back.
            {"key": "daily", "label": "今日の挑戦", "type": "flag", "default": False},
        ],
    }


#: Names the preamble introduces, held to by a test like the other
#: preambles': a template that happened to define ``tuneNum`` would break
#: only in the generated page.
PREAMBLE_NAMES: tuple[str, ...] = (
    "tuneNum",
    "tuneText",
    "tuneFlag",
    "tuneValues",
    "tuneSet",
    "tuneReset",
    "tunePanel",
    "tuneFacts",
    "TUNE_ACCENT",
)

TUNE_PREAMBLE = """
/* --- tuning panel: the page's own form (knowledge base §9 学び 4) ----- */
const TUNE_SPEC=TUNE_SPEC_TOKEN;
const TUNE_KEY='sidra.tune.'+TUNE_SPEC.template;
const TUNE_CONTROLS=[];
let TUNE_RELOADS=0;
/* Storage is a best-effort convenience, never a dependency: a browser with
   it switched off gets the page the generator built, not an exception. */
function tuneStore(){try{return (typeof localStorage!=='undefined')?localStorage:null}
  catch(e){return null}}
function tuneRead(){const s=tuneStore();if(!s)return {};
  try{const raw=s.getItem(TUNE_KEY);if(!raw)return {};
    const v=JSON.parse(raw);return (v&&typeof v==='object')?v:{}}catch(e){return {}}}
let TUNE=tuneRead();
function tuneField(key){return TUNE_SPEC.fields.filter(f=>f.key===key)[0]||null}
/* Clamped to the author's own easy..hard span. A stored value from an older
   version of the page, or one somebody typed into devtools, cannot take the
   game outside the range its author shipped. */
function tuneNum(key,fallback){const f=tuneField(key);if(!f)return fallback;
  const v=Number(TUNE[key]);if(!isFinite(v))return fallback;
  const c=Math.min(f.max,Math.max(f.min,v));
  return f.integer?Math.round(c):c}
function tuneText(key,fallback){const f=tuneField(key);if(!f)return fallback;
  const v=TUNE[key];
  return (typeof v==='string'&&/^#[0-9a-fA-F]{6}$/.test(v))?v:fallback}
function tuneChoice(key,fallback){const f=tuneField(key);if(!f)return fallback;
  const v=TUNE[key];
  return (f.choices.indexOf(v)>=0)?v:fallback}
function tuneFlag(key,fallback){const f=tuneField(key);if(!f)return fallback;
  const v=TUNE[key];
  return (typeof v==='boolean')?v:fallback}
function tuneValues(){const o={};TUNE_SPEC.fields.forEach(function(f){
  o[f.key]=f.type==='colour'?tuneText(f.key,f.default)
    :(f.type==='choice'?tuneChoice(f.key,f.default)
    :(f.type==='flag'?tuneFlag(f.key,f.default):tuneNum(f.key,f.default)))});
  return o}
const TUNE_ACCENT=tuneValues().accent;
function tuneWrite(next){const s=tuneStore();if(!s)return false;
  try{s.setItem(TUNE_KEY,JSON.stringify(next));return true}catch(e){return false}}
/* Applying means re-running this same file. Nothing is rebuilt and nothing
   is fetched - the artifact on disk is byte-for-byte what it was. */
function tuneReload(){TUNE_RELOADS++;
  try{if(typeof location!=='undefined'&&location&&typeof location.reload==='function'){
    location.reload()}}catch(e){}}
function tuneSet(key,value){const next=tuneRead();
  const f=tuneField(key);if(!f)return false;
  if(f.type==='choice'){const preset=f.presets[value];if(!preset)return false;
    next[key]=value;next.speed=preset.speed;next.band=preset.band}
  else if(f.type==='flag'){next[key]=!!value}
  else{next[key]=value}
  if(!tuneWrite(next))return false;
  TUNE=next;tuneReload();return true}
function tuneReset(){const s=tuneStore();
  try{if(s)s.removeItem(TUNE_KEY)}catch(e){}
  TUNE={};tuneReload();return true}
function tuneControl(f,value){const row=document.createElement('label');
  row.className='tune-row';
  row.style.cssText='display:flex;gap:10px;align-items:center;margin:6px 0';
  const name=document.createElement('span');name.textContent=f.label;
  name.style.cssText='flex:0 0 9em';row.appendChild(name);
  let input;
  if(f.type==='choice'){input=document.createElement('select');
    f.choices.forEach(function(c){const o=document.createElement('option');
      o.value=c;o.textContent=c;if(c===value){o.selected=true}input.appendChild(o)})}
  else{input=document.createElement('input');
    if(f.type==='colour'){input.type='color';input.value=String(value)}
    else if(f.type==='flag'){input.type='checkbox';input.checked=!!value}
    else{input.type='range';input.min=String(f.min);input.max=String(f.max);
      input.step=String(f.step);input.value=String(value)}}
  input.setAttribute('data-tune',f.key);
  input.addEventListener('change',function(){
    tuneSet(f.key,f.type==='number'?Number(input.value)
      :(f.type==='flag'?!!input.checked:input.value))});
  row.appendChild(input);TUNE_CONTROLS.push(input);return row}
function tunePanel(){
  if(typeof document==='undefined'||!document.createElement)return null;
  const host=(document.querySelector&&document.querySelector('main'))||document.body;
  if(!host||!host.appendChild)return null;
  const box=document.createElement('details');box.id='tune';
  box.style.cssText='margin:18px 0 0;padding:10px 14px;border:1px solid BORDER_TOKEN;'
    +'border-radius:6px;font-size:13px';
  const sum=document.createElement('summary');
  sum.textContent='調整（この端末だけに保存されます）';
  sum.style.cssText='cursor:pointer';box.appendChild(sum);
  const values=tuneValues();
  TUNE_SPEC.fields.forEach(function(f){box.appendChild(tuneControl(f,values[f.key]))});
  const reset=document.createElement('button');reset.type='button';
  reset.textContent='既定に戻す';
  reset.addEventListener('click',tuneReset);box.appendChild(reset);
  host.appendChild(box);return box}
/* What the judge reads back after driving the real controls. */
function tuneFacts(){return {template:TUNE_SPEC.template,
  fields:TUNE_SPEC.fields.map(function(f){return f.key}),
  values:tuneValues(),controls:TUNE_CONTROLS.length,reloads:TUNE_RELOADS}}
if(typeof document!=='undefined'&&document.addEventListener&&document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded',tunePanel)}else{tunePanel()}
"""


#: Drives the page's own panel in node: a stub DOM just complete enough for
#: the form to be built and a control to be moved, and then the values the
#: template body actually ended up with. Grepping for ``<input`` would say
#: nothing about whether the slider changes the game.
PROBE = """
const tuneNothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : tuneNothing),
  apply: () => tuneNothing, set: () => true });
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.requestAnimationFrame = () => 0;
globalThis.addEventListener = () => {};
globalThis.Image = function(){ return tuneNothing };
const TUNE_PROBE_STORE = STORED_INPUT;
let tuneProbeReloads = 0;
globalThis.localStorage = {
  getItem: (k) => (k in TUNE_PROBE_STORE ? TUNE_PROBE_STORE[k] : null),
  setItem: (k, v) => { TUNE_PROBE_STORE[k] = String(v) },
  removeItem: (k) => { delete TUNE_PROBE_STORE[k] } };
globalThis.location = { reload: () => { tuneProbeReloads++ } };
function tuneProbeElement(tag){
  const el = { tagName: tag, style: {}, children: [], attrs: {}, handlers: {},
    appendChild(c){ this.children.push(c); return c },
    setAttribute(k, v){ this.attrs[k] = v },
    getAttribute(k){ return this.attrs[k] },
    addEventListener(name, fn){ (this.handlers[name] = this.handlers[name] || []).push(fn) },
    getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
    getContext: () => tuneNothing,
    width: 720, height: 320 };
  return el }
const TUNE_PROBE_BODY = tuneProbeElement('body');
globalThis.document = { readyState: 'complete', body: TUNE_PROBE_BODY,
  createElement: tuneProbeElement, querySelector: () => null,
  getElementById: () => tuneProbeElement('canvas') };
SCRIPT_PLACEHOLDER
/* Walk the panel the page built, not a list this probe kept. */
function tuneProbeFlatten(el){ return [el].concat((el.children||[]).flatMap(tuneProbeFlatten)) }
const tuneProbeNodes = tuneProbeFlatten(TUNE_PROBE_BODY);
const tuneProbePanel = tuneProbeNodes.filter(n => n.id === 'tune')[0] || null;
const tuneProbeControls = tuneProbeNodes.filter(n => n.attrs && n.attrs['data-tune']);
const tuneProbeButtons = tuneProbeNodes.filter(n => n.tagName === 'button');
const tuneProbeBefore = tuneFacts();
let tuneProbeMoved = null;
const tuneProbeSlider = tuneProbeControls.filter(n => n.getAttribute('data-tune') === 'speed')[0];
if (tuneProbeSlider) {
  /* The far end of the author's own range: a value the page must accept
     and must not have been sitting at already. */
  tuneProbeSlider.value = String(TARGET_INPUT);
  (tuneProbeSlider.handlers.change || []).forEach(fn => fn());
  tuneProbeMoved = tuneRead().speed;
}
let tuneProbeCleared = null;
if (tuneProbeButtons.length) {
  (tuneProbeButtons[0].handlers.click || []).forEach(fn => fn());
  tuneProbeCleared = tuneRead().speed === undefined;
}
console.log(JSON.stringify({
  panel: !!tuneProbePanel,
  controls: tuneProbeControls.map(n => n.getAttribute('data-tune')),
  buttons: tuneProbeButtons.length,
  values: tuneProbeBefore.values,
  speedSeen: SPEED_PROBE,
  accentSeen: TUNE_ACCENT,
  moved: tuneProbeMoved,
  cleared: tuneProbeCleared,
  reloads: tuneProbeReloads,
  stored: Object.keys(TUNE_PROBE_STORE),
}));
"""


def probe_source(script: str, *, stored: dict[str, dict] | None = None, target: float = 0, speed_expr: str = "0") -> str:
    """The page's own script, stubbed enough to build the panel and report.

    ``stored`` is the browser's ``localStorage`` as the probe should find
    it - the way a second visit finds what the first visit saved.
    ``speed_expr`` names the template's own binding for ``SPEED_TOKEN``, so
    the judge reads the number the game body got rather than the number the
    panel says it wrote.
    """

    payload = {key: json.dumps(value, ensure_ascii=False) for key, value in (stored or {}).items()}
    return (
        PROBE.replace("STORED_INPUT", json.dumps(payload, ensure_ascii=False))
        .replace("TARGET_INPUT", json.dumps(target))
        .replace("SPEED_PROBE", speed_expr)
        .replace("SCRIPT_PLACEHOLDER", script)
    )


#: The binding each template gives ``SPEED_TOKEN``. Read by the judge only:
#: the page has no reason to know its own variable's name.
SPEED_BINDING: dict[str, str] = {
    "fishing": "SPEED",
    "catch": "FALL",
    "adventure": "ESPEED",
    "duel": "CSPEED",
    "shooter": "FALL",
    "puzzle": "COLOURS",
    "kaiju": "CRACK",
    "racing": "PACE",
    "platformer": "GAPF",
}


__all__ = [
    "AXIS_LABELS",
    "LADDER",
    "PREAMBLE_NAMES",
    "PROBE",
    "SPEED_BINDING",
    "TUNE_PREAMBLE",
    "panel_schema",
    "probe_source",
]
