"""Can one thumb press what it can see, and does the game move?

C-1982, §8 事実 5 ("満員の動く乗り物で片手・初見で遊べるか" - Voodoo's own
test) and 事実 8 ("開いた瞬間に遊ばせる").

``creation_one_thumb_play``, ``creation_pad_painted`` and
``creation_touch_playable`` all drive the page's own table: they ask
``padButtons()`` where the buttons are and then press exactly there. That
proves the table is consistent with itself. A thumb presses the *screen*:
the canvas is displayed scaled down by CSS, and ``padAt()`` divides the
client coordinates back into canvas space with
``getBoundingClientRect()``. If that division were wrong, what is drawn and
what is pressable would part company, and no existing judge would notice.

So this drives the page with nothing but ``PointerEvent``s of
``pointerType: 'touch'`` - no keyboard anywhere - and reads the result in
pixels:

1. one tap on the canvas starts the game,
2. the button's rectangle has paint in it (you can see what you press),
3. tapping "right" moves the player right - and the button sits on the
   *left* half of the canvas, so a player that merely followed the finger
   would move the other way (measured: the left button takes catch's
   basket from x=379 to x=26),
4. lifting the finger ends the hold and the player stops.

**Two things learned while building this.** The pad only wakes for a touch
pointer, and the start gate swallows the first tap, so the pad needs a
second one. And a 320px window does not narrow this page - the layout
stays 447px wide (C-1970's floor), so width is out of scope here.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.themes import select_theme
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

#: Two templates that move a player sideways on the arrow keys, with the
#: theme token each one paints its player in: catch's tray is the alert
#: colour, the platformer's hero is the accent.
ASKS: dict[str, tuple[str, str]] = {
    "catch": ("ふくろうのキャッチゲームを作って", "alert"),
    "platformer": ("ふくろうのジャンプゲームを作って", "accent"),
}

#: How far the player must travel for a press to count, in canvas pixels.
#: Well past the jitter of a sprite's own animation.
MOVED = 12.0

_TITLE = re.compile(r"<title>THUMB(.*?)</title>", re.S)

_HOOK = """
<script>
window.__q = [];
window.requestAnimationFrame = function(fn){ window.__q.push(fn); return window.__q.length };
</script>
"""

_REPORT = """
<script>
addEventListener('load', function(){
  setTimeout(function(){
    const out = {};
    try {
      let T = 0;
      const step = function(n){
        for (let k = 0; k < n && window.__q.length; k++) {
          const due = window.__q; window.__q = []; T += 16;
          due.forEach(function(fn){ fn(T) }) } };
      step(4);
      const cv = document.querySelector('canvas');
      const cx = cv.getContext('2d');
      const want = [PLAYER_R, PLAYER_G, PLAYER_B];
      /* Where the player is, in canvas pixels, from the paint itself. */
      const where = function(){
        const d = cx.getImageData(0, 0, cv.width, cv.height).data;
        let sum = 0, n = 0;
        for (let y = 0; y < cv.height; y++) {
          for (let x = 0; x < cv.width; x++) {
            const i = (y * cv.width + x) * 4;
            if (d[i] === want[0] && d[i + 1] === want[1] && d[i + 2] === want[2]) { sum += x; n++ } } }
        return n ? +(sum / n).toFixed(1) : null };
      /* A thumb, and nothing else: no key event is built anywhere here. */
      const touch = function(type, x, y){
        cv.dispatchEvent(new PointerEvent(type, {clientX: x, clientY: y,
          pointerType: 'touch', pointerId: 1, isPrimary: true,
          bubbles: true, cancelable: true})) };
      const frame = function(){ return cv.getBoundingClientRect() };
      const first = frame();
      touch('pointerdown', first.left + first.width / 2, first.top + first.height / 2);
      touch('pointerup', first.left + first.width / 2, first.top + first.height / 2);
      step(30);
      out.started = (typeof gateState === 'function') ? String(gateState()) : null;
      /* The pad wakes for a touch pointer; the gate swallowed the first. */
      touch('pointerdown', first.left + 4, first.top + 4);
      touch('pointerup', first.left + 4, first.top + 4);
      step(12);
      const buttons = (typeof padButtons === 'function') ? padButtons() : [];
      out.buttons = buttons.map(function(b){ return b.id });
      const right = buttons.filter(function(b){ return b.id === 'ArrowRight' })[0];
      if (!right) { out.err = 'no right button on the pad';
        document.title = 'THUMB' + JSON.stringify(out); return }
      /* Is anything drawn where the page says the button is? */
      const paint = cx.getImageData(right.x | 0, right.y | 0,
        Math.max(1, right.w | 0), Math.max(1, right.h | 0)).data;
      const corner = [paint[0], paint[1], paint[2]];
      let other = 0;
      for (let i = 0; i < paint.length; i += 4) {
        if (paint[i] !== corner[0] || paint[i + 1] !== corner[1] || paint[i + 2] !== corner[2]) other++ }
      out.painted = +(other / (paint.length / 4)).toFixed(3);
      const r = frame();
      const sx = r.width / cv.width, sy = r.height / cv.height;
      const px = r.left + (right.x + right.w / 2) * sx;
      const py = r.top + (right.y + right.h / 2) * sy;
      /* The button's own place on the canvas, so "followed the finger" can
         be told from "pressed the button". */
      out.buttonX = +(right.x + right.w / 2).toFixed(1);
      out.middle = cv.width / 2;
      out.before = where();
      touch('pointerdown', px, py);
      step(45);
      out.after = where();
      touch('pointerup', px, py);
      step(20);
      out.held = (typeof PAD_HELD !== 'undefined') ? PAD_HELD.size : null;
      out.resting = where();
      step(20);
      out.stopped = where();
    } catch (e) { out.err = String(e).slice(0, 140) }
    document.title = 'THUMB' + JSON.stringify(out);
  }, 800);
});
</script>
"""


@dataclass(frozen=True)
class ThumbResult:
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _rgb(colour: str) -> tuple[int, int, int]:
    raw = colour.lstrip("#")
    return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def read_template(key: str) -> dict:
    """Drive one page with a thumb and report what the screen did."""

    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    ask, token = ASKS[key]
    player = _rgb(select_theme(ask).tokens[token])
    body = (
        _REPORT.replace("PLAYER_R", str(player[0]))
        .replace("PLAYER_G", str(player[1]))
        .replace("PLAYER_B", str(player[2]))
    )
    html = generate_game(ask).html
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
    seen["template"] = key
    return seen


def evaluate_one_thumb_reaches_the_buttons() -> ThumbResult:
    keys = sorted(ASKS)
    total = len(keys) * 4
    passed = 0
    failures: list[str] = []
    readings: list[str] = []

    for key in keys:
        seen = read_template(key)
        if "err" in seen:
            failures.append(f"{key}: {seen['err']}")
            continue
        readings.append(
            f"{key} start={seen['started']} paint={seen['painted']} "
            f"x {seen['before']}->{seen['after']} button@{seen['buttonX']} held={seen['held']}"
        )
        if seen["started"] == "playing":
            passed += 1
        else:
            failures.append(f"{key}: one tap left the page at {seen['started']!r}")
        if seen["painted"] > 0.1:
            passed += 1
        else:
            failures.append(f"{key}: the button's rectangle is {seen['painted']} painted")
        moved = (
            None
            if seen["before"] is None or seen["after"] is None
            else seen["after"] - seen["before"]
        )
        if moved is not None and moved >= MOVED and seen["buttonX"] < seen["middle"]:
            passed += 1
        elif moved is None:
            failures.append(f"{key}: the player was never found in the paint")
        else:
            failures.append(f"{key}: the right button moved the player {moved:+.1f}px")
        after_lift = (
            None
            if seen["resting"] is None or seen["stopped"] is None
            else abs(seen["stopped"] - seen["resting"])
        )
        if seen["held"] == 0 and after_lift is not None and after_lift < MOVED:
            passed += 1
        else:
            failures.append(
                f"{key}: after the lift {seen['held']} held, the player drifted {after_lift}"
            )

    return ThumbResult(
        checks_passed=passed,
        checks_total=total,
        failures=tuple(failures[:4]),
        readings=tuple(readings),
    )


__all__ = [
    "ASKS",
    "MOVED",
    "ThumbResult",
    "evaluate_one_thumb_reaches_the_buttons",
    "read_template",
]
