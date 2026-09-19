"""Is the creature too big for the frame, with something small beside it?

C-1980, §6 観察 1: "巨大さは全身を見せないことで作られる。部分描写が基本で、
全身の引きは要所に 1 回だけ。小さい存在と同じフレームに入れて対比する。"

``creation_whole_body_is_rare`` holds the *"only once"* half of that
sentence: a recording context counts the frames where torso, shoulder and
head are drawn together, and finds none in 291 frames of fighting. What no
judge holds is the other half - that what *is* on screen is a creature too
big to fit. A leg three pixels wide also never shows a whole body.

So this reads the painted frame in a real browser, in all four themes:

1. the creature's paint touches the frame's edge - it is cut off, which is
   what makes it unseeable in full,
2. the small one (the player, in the accent colour) is in the same frame,
3. the creature outweighs the small one by an order of magnitude.

**Telling the creature from the city.** The creature is painted in the raw
theme colour (``BORDER_TOKEN``); the buildings behind it are the same
colour put through the scene's transform (``scenePaint('BORDER_TOKEN')``),
which moves the hue. Counting the raw colour alone counts the creature.

**The chosen number.** §6 gives no size. The 10x in check 3 is a choice -
an order of magnitude - made against a measured 30x, and pinned in
``tests/test_the_giant_does_not_fit_the_frame.py`` so the next reader can
see it was chosen rather than measured.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.probekeys import with_probe_keys
from sidra_ai.creation.themes import THEMES
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

ASK = "ふくろうの怪獣ゲームを作って"

#: An order of magnitude, chosen (see the module docstring) against a
#: measured 30x.
SCALE = 10.0

#: Frames to turn before each reading: the awakening holds its own scrim
#: until the fight starts.
WARM = 80

_TITLE = re.compile(r"<title>GIANT(.*?)</title>", re.S)

_HOOK = """
<script>
window.__q = [];
window.requestAnimationFrame = function(fn){ window.__q.push(fn); return window.__q.length };
</script>
"""

_REPORT = """
<script>
PROBE_KEYS_PLACEHOLDER
addEventListener('load', function(){
  setTimeout(function(){
    const out = {frames: []};
    try {
      let T = 0;
      const step = function(n){
        for (let k = 0; k < n && window.__q.length; k++) {
          const due = window.__q; window.__q = []; T += 16;
          due.forEach(function(fn){ fn(T) }) } };
      step(4);
      /* The pair comes from probekeys, not from here (C-1651's ratchet). */
      const pair = probeKey(' ');
      ['keydown', 'keyup'].forEach(function(type){
        const e = new KeyboardEvent(type, {key: pair.key, code: pair.code, bubbles: true});
        document.dispatchEvent(e); window.dispatchEvent(e); });
      const cv = document.querySelector('canvas');
      const cx = cv.getContext('2d');
      const near = function(d, i, want){
        return d[i] === want[0] && d[i + 1] === want[1]
            && d[i + 2] === want[2] };
      const beast = [BEAST_R, BEAST_G, BEAST_B];
      const small = [SMALL_R, SMALL_G, SMALL_B];
      const look = function(){
        const d = cx.getImageData(0, 0, cv.width, cv.height).data;
        let big = 0, edge = 0, mate = 0;
        for (let y = 0; y < cv.height; y++) {
          for (let x = 0; x < cv.width; x++) {
            const i = (y * cv.width + x) * 4;
            if (near(d, i, beast)) { big++;
              if (x === 0 || y === 0 || x === cv.width - 1 || y === cv.height - 1) edge++ }
            else if (near(d, i, small)) { mate++ } } }
        return {big: big, edge: edge, mate: mate,
                state: (typeof bossFacts === 'function') ? String(bossFacts().state) : null};
      };
      for (let i = 0; i < 4; i++) { step(WARM_TOKEN); out.frames.push(look()) }
      out.size = [cv.width, cv.height];
    } catch (e) { out.err = String(e).slice(0, 140) }
    document.title = 'GIANT' + JSON.stringify(out);
  }, 800);
});
</script>
"""


@dataclass(frozen=True)
class GiantResult:
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    raw = hex_colour.lstrip("#")
    return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def read_theme(name: str) -> dict:
    """What one theme's fight actually paints."""

    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    theme = THEMES[name]
    beast = _rgb(theme.tokens["border"])
    small = _rgb(theme.tokens["accent"])
    body = with_probe_keys(
        _REPORT.replace("WARM_TOKEN", str(WARM))
        .replace("BEAST_R", str(beast[0]))
        .replace("BEAST_G", str(beast[1]))
        .replace("BEAST_B", str(beast[2]))
        .replace("SMALL_R", str(small[0]))
        .replace("SMALL_G", str(small[1]))
        .replace("SMALL_B", str(small[2]))
    )
    html = generate_game(ASK, theme_name=name).html
    with tempfile.TemporaryDirectory() as room:
        page = pathlib.Path(room) / "page.html"
        page.write_text(
            html.replace("<body", _HOOK + "<body", 1).replace("</body>", body + "</body>"),
            encoding="utf-8",
        )
        run = subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--force-prefers-reduced-motion",
                "--virtual-time-budget=9000",
                "--window-size=390,844",
                "--dump-dom",
                f"file://{page}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    found = _TITLE.search(run.stdout)
    seen = json.loads(found.group(1)) if found else {"err": "the page said nothing"}
    seen["theme"] = name
    return seen


def fighting(seen: dict) -> list[dict]:
    """Only the frames the page itself calls a fight."""

    return [f for f in seen.get("frames", []) if f.get("state") == "fight"]


def evaluate_the_giant_does_not_fit_the_frame() -> GiantResult:
    names = sorted(THEMES)
    total = len(names) * 3
    passed = 0
    failures: list[str] = []
    readings: list[str] = []

    for name in names:
        seen = read_theme(name)
        if "err" in seen:
            failures.append(f"{name}: {seen['err']}")
            continue
        frames = fighting(seen)
        if not frames:
            failures.append(f"{name}: the fight never started")
            continue
        area = seen["size"][0] * seen["size"][1]
        big = max(f["big"] for f in frames)
        edge = max(f["edge"] for f in frames)
        mate = max(f["mate"] for f in frames)
        readings.append(
            f"{name} creature={big / area:.1%} edge={edge}px small={mate / area:.1%} "
            f"scale={(big / mate):.0f}x" if mate else f"{name} creature={big / area:.1%} small=0"
        )
        if edge > 0:
            passed += 1
        else:
            failures.append(f"{name}: the creature fits inside the frame ({big} px, no edge)")
        if mate > 0:
            passed += 1
        else:
            failures.append(f"{name}: nothing small shares the frame")
        if mate > 0 and big >= mate * SCALE:
            passed += 1
        else:
            failures.append(
                f"{name}: the creature is {big / mate:.1f}x the small one"
                if mate
                else f"{name}: no small one to be bigger than"
            )

    return GiantResult(
        checks_passed=passed,
        checks_total=total,
        failures=tuple(failures[:4]),
        readings=tuple(readings),
    )


__all__ = [
    "ASK",
    "GiantResult",
    "SCALE",
    "WARM",
    "evaluate_the_giant_does_not_fit_the_frame",
    "fighting",
    "read_theme",
]
