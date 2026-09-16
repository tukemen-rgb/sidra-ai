"""Is the end screen's headline actually centred, by the font's own metrics?

§35 事実 1 says `measureText` returns 「the text's advance width (the width
of that inline box) in CSS pixels」 - a number the font owns. 事実 2 says a
wide character takes one Em and a narrow one about half, so `文字数 × サイズ`
is the assumption that every character is full-width.

Seven templates centred their result line that way, and the assumption is
exact for a line with no digits in it: 「巨獣、沈黙。」 measured 120.0 either
way. The moment a score joins the sentence it drifts left, and it drifts
further as the score grows - 「撃墜 999 機・得点 1234567。」 came out 51.7px
off centre. A short sample looks correct, which is how it lasted.

Nothing could catch it from Python. The HUD judges measure contrast, the
text floor, the palette and whether a thing was painted at all; none of
them knows how wide a string is, because that is a fact about the font
rather than about the page. So this judge asks the engine: it opens the
real generated page in the Chromium this machine has, wraps `fillText` to
record what was drawn and where, forces each template's own end state, and
then - still inside the browser - asks `measureText` for the true width
and compares the drawn left edge with the centre it should have had.

Both idioms are read the same way. `textAlign='center'` means the x that
was passed is the middle, so the left edge is x - width/2; the default
means x IS the left edge. What is checked is where the ink lands, not
which idiom put it there, so a template may change idiom without this
judge caring - and marble, which already used the engine's own centring
before C-1896, passes without being special-cased.

When there is no Chromium this returns a result that says so rather than
a pass. A judge that cannot run is not evidence that a page is correct
(the rule `creation/browser.py` was written under).
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.creation.browser import chromium_path

_PROBE_ID = "sidra-endtext-probe"

#: How far the ink may sit from the true centre. One pixel of slack for
#: the engine's own rounding; the defect this was written for was 51.7.
TOLERANCE_PX = 1.5

#: The HUD runs at 13px and every end screen's headline at 20. A "biggest
#: line" that is no bigger than the HUD means the end screen never came
#: up, and the judge would otherwise quietly measure the score band
#: instead - which is how marble first came back -192.9px off centre for a
#: line it was never asked about.
HEADLINE_MIN_PX = 14.0

#: The request that makes each page, and the one line of the page's own
#: state that puts it on its end screen. Set through the page's own
#: globals - no drawing is faked, the page draws its result itself.
END_STATES: dict[str, tuple[str, str]] = {
    "adventure": ("冒険ゲームを作って", "state='win'"),
    "duel": ("ビームで撃ち合うゲームを作って", "state='end';winner='決着。'"),
    "kaiju": ("巨大怪獣と戦うゲームを作って", "state='won'"),
    "platformer": ("横スクロールのアクションゲームを作って", "state='goal'"),
    "puzzle": ("同じ色を消すパズルを作って", "state='over'"),
    "racing": ("レースゲームを作って", "state='goal'"),
    "shooter": ("シューティングゲームを作って", "state='over'"),
    # marble already centred through the engine before C-1896; it is here
    # so that stays true, not as an exception.
    "marble": ("転がる玉のゲームを作って", "state='over';over='コースを走り切った。'"),
}

#: Templates with no end screen to centre, and why. Written down so that
#: leaving a page out is a decision rather than an omission - the table
#: is checked against the product's own template list below.
NO_END_SCREEN: dict[str, str] = {
    "catch": "終幕の一枚を持たず、HUD の行だけを左端から描く",
    "fishing": "同じく——得点も操作案内も x=40 の左寄せで、中央に置く行が無い",
}

#: A score that is mostly digits, because the drift grows with the narrow
#: characters and a default score of 0 hides it almost completely.
_LOADED = "try{score=1234567}catch(e){};try{kills=999}catch(e){};"

_READER = """<script>(function(){
var out={lines:[],error:null};
try{
  var cv=document.getElementById('stage')||document.querySelector('canvas');
  var cx=cv.getContext('2d');
  var seen=[];
  var real=cx.fillText.bind(cx);
  cx.fillText=function(t,x,y){
    seen.push({t:String(t),x:x,y:y,font:cx.font,align:cx.textAlign});
    return real(t,x,y)};
  STATE_PLACEHOLDER
  seen.length=0;
  if(typeof draw==='function'){draw(performance.now())}
  else if(typeof step==='function'){step(performance.now())}
  /* Measure with the same font each line was drawn in, so the width is
     the one the engine used for that line and not a later one. */
  var keep=cx.font, keepAlign=cx.textAlign;
  for(var i=0;i<seen.length;i++){
    var s=seen[i];
    cx.font=s.font;
    s.width=cx.measureText(s.t).width;
    s.left=(s.align==='center')?s.x-s.width/2:
           (s.align==='right')?s.x-s.width:s.x;
    s.canvas=cv.width;
  }
  cx.font=keep;cx.textAlign=keepAlign;
  out.lines=seen;
}catch(e){out.error=String(e&&e.message||e)}
var d=document.createElement('div');d.id='PROBE_ID_PLACEHOLDER';
d.textContent=JSON.stringify(out);document.body.appendChild(d);
})()</script>"""


@dataclass(frozen=True)
class EndTextResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    centred: tuple[str, ...] = ()
    ran: bool = True


def _read(html: str, state: str, *, timeout: int = 120) -> dict | None:
    browser = chromium_path()
    if browser is None:
        return None
    reader = _READER.replace("STATE_PLACEHOLDER", _LOADED + "try{" + state + "}catch(e){}")
    reader = reader.replace("PROBE_ID_PLACEHOLDER", _PROBE_ID)
    with tempfile.TemporaryDirectory() as home:
        target = Path(home) / "page.html"
        target.write_text(html + reader, encoding="utf-8")
        try:
            run = subprocess.run(
                [
                    browser, "--headless", "--disable-gpu", "--no-sandbox",
                    f"--user-data-dir={home}/profile", "--dump-dom",
                    target.as_uri(),
                ],
                capture_output=True, text=True, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None
    if run.returncode != 0:
        return None
    found = re.search(rf'id="{_PROBE_ID}">(.*?)</div>', run.stdout, re.S)
    if found is None:
        return None
    try:
        return json.loads(found.group(1))
    except ValueError:
        return None


def _headline(lines: list[dict]) -> dict | None:
    """The result line: the biggest type on the end screen.

    Picked by font size rather than by position, because the templates put
    their headline at different heights and one of them (racing) sits it
    above a lap table that is deliberately NOT centred.
    """

    best, best_px = None, 0.0
    for line in lines:
        match = re.match(r"\s*([0-9.]+)px", str(line.get("font", "")))
        if not match or not str(line.get("t", "")).strip():
            continue
        px = float(match.group(1))
        if px > best_px:
            best, best_px = line, px
    return best


def evaluate_end_text_is_centred() -> EndTextResult:
    from sidra_ai.creation.games import generate_game

    if chromium_path() is None:
        return EndTextResult(
            passed=False, checks_passed=0, checks_total=0, ran=False,
            failures=("no Chromium on this machine; the question was not asked",),
        )

    failures: list[str] = []
    centred: list[str] = []
    checks = 0
    for template, (request, state) in sorted(END_STATES.items()):
        page = generate_game(request).html
        out = _read(page, state)
        if out is None:
            failures.append(f"{template}: the page could not be read in the browser")
            continue
        if out.get("error"):
            failures.append(f"{template}: {out['error'][:70]}")
            continue
        line = _headline(out.get("lines") or [])
        if line is None:
            failures.append(f"{template}: the end screen drew no text")
            continue
        headline_px = float(re.match(r"\s*([0-9.]+)px", str(line["font"])).group(1))
        if headline_px < HEADLINE_MIN_PX:
            failures.append(
                f"{template}: the biggest line was {headline_px:.0f}px "
                "- the end screen never came up"
            )
            continue
        width = float(line["width"])
        if width <= 0:
            failures.append(f"{template}: the headline measured no width")
            continue
        want = (float(line["canvas"]) - width) / 2.0
        off = float(line["left"]) - want
        if abs(off) > TOLERANCE_PX:
            failures.append(
                f"{template}: 「{line['t'][:22]}」 sits {off:+.1f}px off centre"
            )
            continue
        checks += 1
        centred.append(f"{template}({off:+.1f}px)")

    # Every template the product ships is either measured here or has a
    # written reason for not being. Without this, the cheapest way to a
    # clean sheet is to stop opening a page (C-1887, C-1891, C-1894).
    from sidra_ai.creation.games import TEMPLATES

    named = set(END_STATES) | set(NO_END_SCREEN)
    # A page cannot be both measured and excused. Allowing the overlap let
    # a false excuse ride along unnoticed while the page was still being
    # opened - harmless today, and a lie waiting for the day the page is
    # dropped from END_STATES.
    for template in sorted(set(END_STATES) & set(NO_END_SCREEN)):
        failures.append(f"{template} is both measured and excused")
    for template in sorted(set(TEMPLATES) - named):
        failures.append(f"{template} is neither measured nor explained")
    for template in sorted(named - set(TEMPLATES)):
        failures.append(f"{template} is named here but the product has no such template")
    if named == set(TEMPLATES):
        checks += 1

    return EndTextResult(
        passed=not failures and checks == len(END_STATES) + 1,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        centred=tuple(centred),
    )
