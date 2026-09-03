"""Key re-assignment for every generated game. The last §4 basic.

The accessibility guideline list the knowledge base carries
(``docs/research/game-design-notes.md`` §4) has five basics: contrast,
never colour alone, touch targets, **allow control re-assignment**, avoid
flashing. Four were built (C-1018/C-1019 and the flash budget); this is
the fifth. A player whose left hand cannot reach the arrows, or whose
space bar is broken, could not play a single SIDRA game until now.

Mechanism: this preamble is installed before *anything* registers a key
handler. It wraps ``addEventListener`` so every keydown/keyup handler in
the page - the gate's, the preambles', the template's - receives a
translated event: a physical key with a stored assignment arrives as the
canonical key the game reads; everything else passes through untouched,
so an empty map costs nothing and changes nothing.

The map lives in ``localStorage`` under ``sidra.keys.<template>`` - the
same this-device-only boundary the tuning panel uses, nothing sent
anywhere. The UI is the panel's shape too: a ``details`` form listing
only the keys this template actually reads (computed at build time from
the same parser the touch judge uses), each with a button that captures
the next physical key pressed. Assignments are aliases at heart - an
unmapped original keeps working - but a remapped original follows its
owner's instruction like any other key, so swapping two keys behaves the
way the person asked.

The touch pad is unaffected in the default state: it synthesises the
canonical keys, which are identity-mapped until their owner says
otherwise.
"""

from __future__ import annotations

import json

from sidra_ai.creation.touchpad import keys_read

#: Names this preamble introduces, for the vocabulary test.
PREAMBLE_NAMES: tuple[str, ...] = (
    "remapSet",
    "remapReset",
    "remapFacts",
    "REMAP",
)

#: Friendly labels for the keys templates read today; anything unknown is
#: shown as itself.
KEY_LABELS: dict[str, str] = {
    "ArrowLeft": "←（左）",
    "ArrowRight": "→（右）",
    "ArrowUp": "↑（上）",
    "ArrowDown": "↓（下）",
    " ": "SPACE（アクション）",
    "a": "A",
    "d": "D",
    "r": "R（やり直し）",
    "p": "P",
}

REMAP_PREAMBLE = """
/* --- key re-assignment (game-design-notes.md §4): installed before any
   handler exists, so every listener in the page hears translated keys.
   An empty map is the identity; the stored one is this device's own. */
const REMAP_NAME=REMAP_NAME_INPUT,REMAP_ACTIONS=REMAP_ACTIONS_INPUT;
const REMAP_KEY='sidra.keys.'+REMAP_NAME;
function remapStore(){try{return (typeof localStorage!=='undefined')?localStorage:null}
  catch(e){return null}}
function remapRead(){const s=remapStore();if(!s)return {};
  try{const raw=s.getItem(REMAP_KEY);if(!raw)return {};
    const v=JSON.parse(raw);if(!v||typeof v!=='object')return {};
    /* Only assignments onto keys this game actually reads survive the
       read: stale storage cannot invent a control. */
    const out={};Object.keys(v).forEach(function(k){
      if(REMAP_ACTIONS.indexOf(v[k])>=0)out[k]=v[k]});
    return out}catch(e){return {}}}
let REMAP=remapRead();
let REMAP_WAIT=null;
function remapCode(k){return k===' '?'Space':(k.length===1?'Key'+k.toUpperCase():k)}
function remapEvent(e){
  const from=(typeof e.key==='string')?e.key:'';
  const to=REMAP[from]!==undefined?REMAP[from]:REMAP[from.toLowerCase()];
  if(to===undefined)return e;
  return {key:to,code:remapCode(to),
    preventDefault:function(){if(e.preventDefault)e.preventDefault()},
    stopImmediatePropagation:function(){
      if(e.stopImmediatePropagation)e.stopImmediatePropagation()}}}
const REMAP_AEL=addEventListener;
globalThis.addEventListener=function(type,fn,opt){
  if(type!=='keydown'&&type!=='keyup')return REMAP_AEL(type,fn,opt);
  return REMAP_AEL(type,function(e){
    /* While the form waits for a key, the press it captures must not
       reach the game underneath. */
    if(REMAP_WAIT&&type==='keydown')return;
    fn(remapEvent(e))},opt)};
/* The capture listener is registered RAW, so it hears the physical key. */
REMAP_AEL('keydown',function(e){
  if(!REMAP_WAIT)return;
  if(e.preventDefault)e.preventDefault();
  const target=REMAP_WAIT.target,done=REMAP_WAIT.done;REMAP_WAIT=null;
  remapSet(e.key,target);if(done)done(e.key)});
function remapWrite(next){const s=remapStore();if(!s)return false;
  try{s.setItem(REMAP_KEY,JSON.stringify(next));return true}catch(e){return false}}
function remapSet(physical,target){
  if(REMAP_ACTIONS.indexOf(target)<0)return false;
  if(typeof physical!=='string'||!physical)return false;
  const next=remapRead();next[physical]=target;
  REMAP=next;remapWrite(next);return true}
function remapReset(){const s=remapStore();
  try{if(s)s.removeItem(REMAP_KEY)}catch(e){}
  REMAP={};return true}
/* The form, in the tuning panel's shape: this device only, and only the
   keys this game actually reads. */
const REMAP_LABELS=REMAP_LABELS_INPUT;
let REMAP_ROWS=0;
function remapPanel(){
  if(typeof document==='undefined'||!document.createElement)return null;
  if(!REMAP_ACTIONS.length)return null;
  const host=(document.querySelector&&document.querySelector('main'))||document.body;
  if(!host||!host.appendChild)return null;
  const box=document.createElement('details');box.id='remap';
  box.style.cssText='margin:12px 0 0;padding:10px 14px;border:1px solid BORDER_TOKEN;'
    +'border-radius:6px;font-size:13px';
  const sum=document.createElement('summary');
  sum.textContent='キー設定（この端末だけに保存されます）';
  sum.style.cssText='cursor:pointer';box.appendChild(sum);
  REMAP_ACTIONS.forEach(function(action){
    const row=document.createElement('div');
    row.style.cssText='display:flex;gap:10px;align-items:center;margin:6px 0';
    const name=document.createElement('span');
    name.textContent=REMAP_LABELS[action]||action;
    name.style.cssText='min-width:10em';row.appendChild(name);
    const now=document.createElement('span');
    function said(){const extra=Object.keys(REMAP).filter(function(k){
        return REMAP[k]===action});
      now.textContent=extra.length?('割り当て: '+extra.join(', ')):'既定のまま'}
    said();row.appendChild(now);
    const btn=document.createElement('button');btn.type='button';
    btn.textContent='キーを押して変更';
    btn.setAttribute('data-remap',action===' '?'space':action);
    btn.addEventListener('click',function(){
      btn.textContent='どれかキーを押してください…';
      REMAP_WAIT={target:action,done:function(){
        btn.textContent='キーを押して変更';said()}}});
    row.appendChild(btn);box.appendChild(row);REMAP_ROWS++});
  const reset=document.createElement('button');reset.type='button';
  reset.textContent='キーを既定に戻す';
  reset.setAttribute('data-remap-reset','1');
  reset.addEventListener('click',function(){remapReset();
    box.querySelectorAll&&box.querySelectorAll('span');});
  box.appendChild(reset);
  host.appendChild(box);return box}
if(typeof document!=='undefined'&&document.addEventListener&&document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded',remapPanel)}else{remapPanel()}
function remapFacts(){return {template:REMAP_NAME,actions:REMAP_ACTIONS.slice(),
  map:JSON.parse(JSON.stringify(REMAP)),rows:REMAP_ROWS,
  waiting:REMAP_WAIT!==null}}
"""

#: Stable presentation order for the form: movement, action, the rest.
_ORDER: tuple[str, ...] = ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " ", "r")


def preamble_for(template: str, script: str) -> str:
    """The remap preamble for one template.

    The re-assignable actions are exactly the keys the template's own
    handlers read - found by the same parser the touch judge uses, so the
    form can never offer a control the game does not have.
    """

    read = keys_read(script)
    actions = [k for k in _ORDER if k in read] + sorted(read - set(_ORDER))
    labels = {k: KEY_LABELS.get(k, k) for k in actions}
    return (
        REMAP_PREAMBLE.replace("REMAP_NAME_INPUT", json.dumps(template))
        .replace("REMAP_ACTIONS_INPUT", json.dumps(actions))
        .replace("REMAP_LABELS_INPUT", json.dumps(labels, ensure_ascii=False))
    )


#: The page driven in node: a key with no assignment does nothing the game
#: notices, the same key moves the game once assigned, and the canonical
#: key it aliases still works - read off the running template, not the map.
PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
const REMAP_PROBE_STORE = {};
globalThis.localStorage = {
  getItem: (k) => (k in REMAP_PROBE_STORE ? REMAP_PROBE_STORE[k] : null),
  setItem: (k, v) => { REMAP_PROBE_STORE[k] = String(v) },
  removeItem: (k) => { delete REMAP_PROBE_STORE[k] } };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }) };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
let F = 0;
function run(n){ for (let i = 0; i < n && queued; i++) { const fn = queued; queued = null; fn((F++) * 16) } }
function key(k){
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){} };
  (handlers.keydown || []).forEach(fn => fn(e));
  (handlers.keyup || []).forEach(fn => fn(e));
}
/* Past the briefing, and let the board settle. */
key(' ');
run(40);
const start = puzzleFacts().cur.x;
/* An unassigned key is nobody's control. */
key('j');
const afterRaw = puzzleFacts().cur.x;
/* Assigned, the same key is the control it aliases. */
const accepted = remapSet('j', 'ArrowRight');
const refused = remapSet('j', 'NoSuchKey');
key('j');
const afterMapped = puzzleFacts().cur.x;
/* And the canonical key still works. */
key('ArrowRight');
const afterCanon = puzzleFacts().cur.x;
console.log(JSON.stringify({
  accepted: accepted, refused: refused,
  start: start, afterRaw: afterRaw,
  afterMapped: afterMapped, afterCanon: afterCanon,
  stored: REMAP_PROBE_STORE['sidra.keys.puzzle'] || null,
  actions: remapFacts().actions,
}));
"""


def probe_source(script: str) -> str:
    """The page's own script, wrapped so a re-assignment can be watched."""

    return PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = [
    "KEY_LABELS",
    "PREAMBLE_NAMES",
    "PROBE",
    "REMAP_PREAMBLE",
    "preamble_for",
    "probe_source",
]
