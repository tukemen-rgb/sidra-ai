"""A generated game has 16.67 ms to produce a frame. It should use far less.

The pages are the part of this project a person actually holds - on a phone,
where the drawing itself is not free and the browser has other work. So the
logic inside one frame has to be a rounding error against the budget, not a
close call.

Measured on this container, all ten templates: p95 frame between 0.05 ms and
0.34 ms, worst single frame 2.4 ms - fifty to three hundred times of room.
The threshold below is deliberately loose against that (a slow machine can be
ten times slower and still pass) because what it guards against is a template
that becomes *categorically* heavier - a per-frame loop over everything, a
per-frame allocation of the world - not a few percent of drift.

What this measures is the JavaScript, with the canvas stubbed: the real cost
of rasterising is the browser's and is not reproducible here. That is the
honest scope. A template whose logic is cheap can still draw expensively, and
this will not catch that.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402

#: One frame at 60fps is 16.67 ms. Twelve times the measured worst p95 and
#: still a quarter of the budget: a machine four times slower than this one
#: passes, and a template that got a hundred times heavier does not.
FRAME_BUDGET_MS = 4.0

#: Fifteen seconds of play at 60fps - long enough for a round to reach its
#: later phases, where the scene and the enemies are at their busiest.
FRAMES = 900

_ASKS = {
    "fishing": "釣りゲームを作って",
    "catch": "落ちてくるものを受け止めるゲームを作って",
    "adventure": "冒険ゲームを作って",
    "duel": "ビームの撃ち合いゲームを作って",
    "shooter": "シューティングゲームを作って",
    "puzzle": "パズルゲームを作って",
    "kaiju": "巨大な怪獣と戦うゲームを作って",
    "racing": "レースゲームを作って",
    "platformer": "横スクロールのゲームを作って",
    "marble": "転がる玉のゲームを作って",
}

_HARNESS = r"""
const FRAMES = __FRAMES__;
let rafQueue = [];
let now = 0;
const listeners = {};
function stubCtx(){
  const noop = ()=>{};
  return new Proxy({}, {get:(t,k)=>{
    if (k==='canvas') return canvas;
    if (k==='measureText') return ()=>({width:10});
    if (k==='createLinearGradient'||k==='createRadialGradient')
      return ()=>({addColorStop:noop});
    if (k==='getImageData') return ()=>({data:new Uint8ClampedArray(4)});
    return noop;
  }, set:()=>true});
}
const canvas = {width:720,height:320,getContext:stubCtx,
  addEventListener:(t,f)=>{(listeners[t]=listeners[t]||[]).push(f)},
  removeEventListener:()=>{},
  getBoundingClientRect:()=>({left:0,top:0,width:720,height:320}),
  style:{}, focus:()=>{}, setAttribute:()=>{}, toDataURL:()=>""};
global.document = {
  getElementById:(id)=> id==='stage' ? canvas : null,
  createElement:()=>({style:{}, getContext:stubCtx, appendChild:()=>{},
    setAttribute:()=>{}, classList:{add:()=>{},remove:()=>{}},
    addEventListener:()=>{}, focus:()=>{}}),
  addEventListener:(t,f)=>{(listeners[t]=listeners[t]||[]).push(f)},
  removeEventListener:()=>{}, body:{appendChild:()=>{}, style:{}},
  querySelector:()=>null, querySelectorAll:()=>[], hidden:false,
  documentElement:{style:{}}, hasFocus:()=>true};
global.window = global;
global.navigator = {maxTouchPoints:0, userAgent:"node",
  clipboard:{writeText:()=>Promise.resolve()}, vibrate:()=>{}};
global.localStorage = {getItem:()=>null, setItem:()=>{}, removeItem:()=>{}};
global.matchMedia = ()=>({matches:false, addEventListener:()=>{}, addListener:()=>{}});
global.AudioContext = function(){ return {
  createOscillator:()=>({connect:()=>{},start:()=>{},stop:()=>{},type:"",
    frequency:{setValueAtTime:()=>{},linearRampToValueAtTime:()=>{},
               exponentialRampToValueAtTime:()=>{}}}),
  createGain:()=>({connect:()=>{},gain:{setValueAtTime:()=>{},
    linearRampToValueAtTime:()=>{},exponentialRampToValueAtTime:()=>{},value:0}}),
  createBiquadFilter:()=>({connect:()=>{},frequency:{setValueAtTime:()=>{}},type:""}),
  destination:{}, currentTime:0, state:"running",
  resume:()=>Promise.resolve(), close:()=>{} };};
global.webkitAudioContext = global.AudioContext;
global.requestAnimationFrame = (fn)=>{ rafQueue.push(fn); return rafQueue.length; };
global.cancelAnimationFrame = ()=>{};
global.performance = {now:()=>now};
global.addEventListener = (t,f)=>{(listeners[t]=listeners[t]||[]).push(f)};
global.removeEventListener = ()=>{};
global.setTimeout = ()=>0; global.setInterval = ()=>0;
global.clearInterval = ()=>{}; global.clearTimeout = ()=>{};
try { __SCRIPT__ } catch (e) { console.log(JSON.stringify({error:String(e)})); process.exit(0); }
function press(code){
  (listeners['keydown']||[]).forEach(f=>{
    try{ f({code:code, key:(code==='Space'?' ':code), preventDefault(){}, repeat:false}); }catch(e){}
  });
}
press('Space');
const times = [];
for (let i=0;i<FRAMES;i++){
  now += 16.67;
  const q = rafQueue; rafQueue = [];
  const t0 = process.hrtime.bigint();
  for (const fn of q){ try{ fn(now); }catch(e){} }
  times.push(Number(process.hrtime.bigint()-t0)/1e6);
  if (i % 120 === 0){ press('ArrowRight'); }
}
times.sort((a,b)=>a-b);
console.log(JSON.stringify({
  frames: times.length,
  p95: times[Math.floor(times.length*0.95)],
  max: times[times.length-1]}));
"""


def _play(template_key: str, ask: str) -> dict:
    game = generate_game(ask)
    assert game.template == template_key, (
        f"{ask!r} built {game.template}, not {template_key}"
    )
    match = re.search(r"<script>(.*?)</script>", game.html, re.S)
    assert match, "the page carries no script"
    harness = _HARNESS.replace("__FRAMES__", str(FRAMES)).replace(
        "__SCRIPT__", match.group(1)
    )
    handle = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    try:
        handle.write(harness)
        handle.close()
        result = subprocess.run(
            ["node", handle.name], capture_output=True, text=True, timeout=300
        )
    finally:
        os.unlink(handle.name)
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    assert lines, f"the page produced no reading: {result.stderr[:200]}"
    return json.loads(lines[-1])


@pytest.mark.parametrize("template_key,ask", sorted(_ASKS.items()))
def test_a_frame_costs_a_fraction_of_its_budget(template_key: str, ask: str) -> None:
    if shutil_which_node() is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the page")

    reading = _play(template_key, ask)

    assert "error" not in reading, reading.get("error")
    assert reading["frames"] == FRAMES
    assert reading["p95"] < FRAME_BUDGET_MS, (
        f"{template_key}: p95 frame {reading['p95']:.3f} ms against a "
        f"{FRAME_BUDGET_MS} ms threshold (budget is 16.67 ms)"
    )


def test_every_template_is_covered() -> None:
    """A template added without a reading here would be unmeasured, quietly."""

    assert set(_ASKS) == set(TEMPLATES)


def shutil_which_node():
    import shutil

    return shutil.which("node")
