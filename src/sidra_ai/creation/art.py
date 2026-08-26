"""Generative art pages: seeded, self-contained, on the GAMEYARD palette.

Two patterns ship, chosen from the request the way game templates are:

* ``flow`` - a flow field. Particles ride a smoothly varying vector field
  and leave fading cyan streaks on the dark foundation.
* ``orbits`` - nested epicycles. Points circle centres that circle other
  centres; magenta appears sparingly, per DESIGN.md's own rule.

Determinism is the contract, same as every generator here: the seed is
derived from the request and injected into the page, and the page's own
PRNG (an inline mulberry32) uses only that seed, so 「同じ依頼」 tomorrow
renders the same picture. ``Math.random`` never appears - a page that
draws differently each open cannot honestly be called "the art SIDRA made
for that request".

The page follows the rules the game pages established and the validator
enforces: everything inline, no fetches, and ``prefers-reduced-motion``
renders one finished still frame instead of animating - the artwork, not a
blank canvas.
"""

from __future__ import annotations

import unicodedata
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from sidra_ai.creation.games import _javascript_parses, _no_external_assets, _script_of

#: The DESIGN.md tokens, written once so the page and the tests agree.
BG = "#05070f"
SURFACE = "#0a0f1c"
CYAN = "#2ee6ff"
MAGENTA = "#ff5cc8"

PATTERNS: tuple[str, ...] = ("flow", "orbits")

_PATTERN_WORDS: dict[str, tuple[str, ...]] = {
    "flow": ("フロー", "流れ", "flow", "風", "波"),
    "orbits": ("軌道", "円", "リング", "orbit", "ring", "惑星"),
}


@dataclass(frozen=True)
class GeneratedArt:
    title: str
    pattern: str
    seed: int
    html: str
    evidence: tuple[str, ...] = field(default_factory=tuple)


def choose_pattern(request: str) -> str:
    text = unicodedata.normalize("NFKC", request).casefold()
    for pattern, words in _PATTERN_WORDS.items():
        if any(word.casefold() in text for word in words):
            return pattern
    return "flow"


def _title_from(request: str) -> str:
    import re

    stripped = re.split(r"を?(?:作って|作成して|生成して|つくって|描いて)", request)[0]
    stripped = re.sub(r"[をのはがにで]+$", "", stripped.strip()).strip()
    return stripped[:60] or "ジェネラティブアート"


#: Shared page shell. The script differs per pattern; the rules do not.
_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ margin: 0; background: {bg}; display: grid; place-items: center;
         min-height: 100vh; font-family: system-ui, sans-serif; }}
  canvas {{ background: {bg}; max-width: 100%; height: auto;
            box-shadow: 0 0 40px {surface}; }}
  p {{ color: {cyan}; opacity: .6; font-size: .75rem; }}
</style>
</head>
<body>
<canvas id="c" width="640" height="400"></canvas>
<p>{title} — seed {seed}</p>
<script>
"use strict";
var SEED = {seed};
// mulberry32: small, seedable, and identical everywhere - the built-in
// unseeded generator offers none of that, and the caption's promise
// ("seed N draws this exact picture") depends on all of it.
function rng(seed) {{
  var a = seed >>> 0;
  return function () {{
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    var t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }};
}}
var canvas = document.getElementById("c");
var ctx = canvas.getContext("2d");
var reduced = window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;
{body}
</script>
</body>
</html>
"""

_FLOW_BODY = """
var random = rng(SEED);
// The field: a few random cosine waves summed into an angle per point.
// Smooth by construction, different per seed, no noise library needed.
var waves = [];
for (var w = 0; w < 4; w++) {
  waves.push({ fx: random() * 0.02, fy: random() * 0.02,
               phase: random() * 6.28318 });
}
function angleAt(x, y) {
  var a = 0;
  for (var i = 0; i < waves.length; i++) {
    a += Math.cos(x * waves[i].fx + y * waves[i].fy + waves[i].phase);
  }
  return a * 1.5;
}
var particles = [];
for (var p = 0; p < 260; p++) {
  particles.push({ x: random() * canvas.width, y: random() * canvas.height,
                   tint: random() });
}
ctx.fillStyle = "%BG%";
ctx.fillRect(0, 0, canvas.width, canvas.height);
function step() {
  ctx.fillStyle = "rgba(5, 7, 15, 0.04)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (var i = 0; i < particles.length; i++) {
    var pt = particles[i];
    var a = angleAt(pt.x, pt.y);
    var nx = pt.x + Math.cos(a) * 1.6;
    var ny = pt.y + Math.sin(a) * 1.6;
    // Magenta stays rare: DESIGN.md calls it an accent, not a colour way.
    ctx.strokeStyle = pt.tint < 0.9 ? "%CYAN%" : "%MAGENTA%";
    ctx.globalAlpha = 0.35;
    ctx.beginPath();
    ctx.moveTo(pt.x, pt.y);
    ctx.lineTo(nx, ny);
    ctx.stroke();
    ctx.globalAlpha = 1;
    pt.x = (nx + canvas.width) % canvas.width;
    pt.y = (ny + canvas.height) % canvas.height;
  }
}
if (reduced) {
  // The finished artwork as a still: run the whole flow at once rather
  // than leaving a viewer who asked for less motion a nearly-empty frame.
  for (var s = 0; s < 420; s++) { step(); }
} else {
  (function loop() { step(); requestAnimationFrame(loop); })();
}
"""

_ORBITS_BODY = """
var random = rng(SEED);
var rings = [];
for (var r = 0; r < 7; r++) {
  rings.push({ radius: 30 + r * 24 + random() * 10,
               speed: (random() - 0.5) * 0.04,
               count: 3 + Math.floor(random() * 5),
               phase: random() * 6.28318,
               tint: random() });
}
var t = 0;
function draw() {
  ctx.fillStyle = "rgba(5, 7, 15, 0.12)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  var cx = canvas.width / 2, cy = canvas.height / 2;
  for (var i = 0; i < rings.length; i++) {
    var ring = rings[i];
    for (var k = 0; k < ring.count; k++) {
      var a = ring.phase + t * ring.speed + (k * 6.28318) / ring.count;
      var wobble = 1 + 0.12 * Math.sin(t * 0.02 + i);
      var x = cx + Math.cos(a) * ring.radius * wobble;
      var y = cy + Math.sin(a) * ring.radius * 0.62 * wobble;
      ctx.fillStyle = ring.tint < 0.85 ? "%CYAN%" : "%MAGENTA%";
      ctx.beginPath();
      ctx.arc(x, y, 2.2, 0, 6.28318);
      ctx.fill();
    }
  }
  t += 1;
}
ctx.fillStyle = "%BG%";
ctx.fillRect(0, 0, canvas.width, canvas.height);
if (reduced) {
  for (var s = 0; s < 600; s++) { draw(); }
} else {
  (function loop() { draw(); requestAnimationFrame(loop); })();
}
"""

_BODIES = {"flow": _FLOW_BODY, "orbits": _ORBITS_BODY}


def generate_art(
    request: str,
    *,
    pattern: str | None = None,
    seed: int | None = None,
    evidence: list[str] | None = None,
) -> GeneratedArt:
    chosen = pattern or choose_pattern(request)
    if chosen not in _BODIES:
        raise ValueError(f"unknown pattern: {chosen!r}")
    actual_seed = zlib.crc32(request.encode("utf-8")) if seed is None else seed
    title = _title_from(request)
    body = (
        _BODIES[chosen]
        .replace("%BG%", BG)
        .replace("%CYAN%", CYAN)
        .replace("%MAGENTA%", MAGENTA)
    )
    html = _PAGE.format(
        title=escape(title),
        bg=BG,
        surface=SURFACE,
        cyan=CYAN,
        seed=actual_seed,
        body=body,
    )
    return GeneratedArt(
        title=title,
        pattern=chosen,
        seed=actual_seed,
        html=html,
        evidence=tuple(evidence or ()),
    )


def save_art(art: GeneratedArt, data_dir: str | Path) -> Path:
    directory = Path(data_dir) / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"art-{art.pattern}-{stamp}.html"
    path.write_text(art.html, encoding="utf-8")
    return path


def validate_art(art: GeneratedArt) -> dict:
    """The page rules, checked on the real text.

    Mirrors the game validator on purpose: canvas present, script parses,
    nothing fetched from anywhere, less motion honoured, and - specific to
    art - no ``Math.random``, because an unseeded page breaks the promise
    the seed line in the page's own caption makes.
    """

    failures: list[str] = []
    script = _script_of(art.html)
    if "<canvas" not in art.html:
        failures.append("no canvas element")
    if not script.strip():
        failures.append("no inline script")
    if not _no_external_assets(art.html):
        failures.append("references something off the page")
    if "prefers-reduced-motion" not in art.html:
        failures.append("ignores prefers-reduced-motion")
    if "Math.random" in art.html:
        failures.append("uses Math.random; the page must draw from its seed")
    if str(art.seed) not in art.html:
        failures.append("the seed is not in the page")
    parses, checker = _javascript_parses(script)
    if not parses:
        failures.append(f"script does not parse ({checker})")

    return {
        "valid": not failures,
        "pattern": art.pattern,
        "seed": art.seed,
        "js_checker": checker,
        "bytes": len(art.html),
        "failures": failures,
    }


__all__ = [
    "BG",
    "CYAN",
    "GeneratedArt",
    "MAGENTA",
    "PATTERNS",
    "choose_pattern",
    "generate_art",
    "save_art",
    "validate_art",
]
