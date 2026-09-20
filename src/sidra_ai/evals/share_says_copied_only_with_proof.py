"""Does the page say "copied" only when something was copied?

C-1988, §8 事実 7 (sharing is how a daily game spreads) and the last of the
three blind spots this loop has been closing - storage (C-1973), sound
(C-1974) and now the clipboard.

Every existing share judge drives a node probe where
``navigator.clipboard.writeText`` is an empty function, so "it copied" is
true by construction. In a real browser it is not: measured at ``file://``
with a synthetic press, ``writeText``'s promise neither resolves nor
rejects (a synthetic event is not user activation) and the old trick,
``document.execCommand('copy')``, returns ``false`` - while the button
changed to "copied" all the same.

This reads that boundary:

1. the page does ask the clipboard,
2. it also tries the old trick rather than trusting a promise it has not
   seen settle,
3. with no proof of either, the button does not claim success,
4. the line it meant to copy is real and is what ``shareFacts()`` reports.

A real press on a real device settles the promise, and the button then
says "copied" - that path is the one this cannot drive, and it is named
here so the next reader knows which half is measured.
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
from sidra_ai.evals.targets_meet_the_size_floor import CHROME

ASK = "ふくろうのキャッチゲームを作って"

#: Frames of the real loop: the round has to end before a result can be
#: bragged about (shareReady() is false until then).
FRAMES = 4200

_TITLE = re.compile(r"<title>SHARECOPY(.*?)</title>", re.S)

#: Watches the two ways a page can put text on a clipboard, without
#: replacing either: the calls run, and what the browser does with them is
#: what gets recorded.
_HOOK = """
<script>
window.__q = [];
window.requestAnimationFrame = function(fn){ window.__q.push(fn); return window.__q.length };
window.__clip = {asked: 0, settled: 0, refused: 0, tried: 0, trick: null};
(function(){
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      const write = navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText = function(text){
        window.__clip.asked++;
        const p = write(text);
        if (p && p.then) { p.then(function(){ window.__clip.settled++ },
                                 function(){ window.__clip.refused++ }) }
        return p };
    }
    if (document.execCommand) {
      const old = document.execCommand.bind(document);
      document.execCommand = function(){
        window.__clip.tried++;
        const ok = old.apply(null, arguments);
        window.__clip.trick = ok;
        return ok };
    }
  } catch (e) { window.__clip.err = String(e).slice(0, 60) }
})();
</script>
"""

_REPORT = """
<script>
PROBE_KEYS_PLACEHOLDER
addEventListener('load', function(){
  setTimeout(function(){
    const out = {};
    try {
      let T = 0;
      const step = function(n){
        for (let k = 0; k < n && window.__q.length; k++) {
          const due = window.__q; window.__q = []; T += 16;
          due.forEach(function(fn){ fn(T) }) } };
      /* One listener, one press: the page listens on the window, and a
         press dispatched to both would run the handler twice. */
      const press = function(k){
        const pair = probeKey(k);
        ['keydown', 'keyup'].forEach(function(type){
          window.dispatchEvent(new KeyboardEvent(type,
            {key: k, code: pair.code, bubbles: true, cancelable: true})) }) };
      step(4);
      press(' ');
      step(FRAMES_TOKEN);
      out.ready = (typeof shareReady === 'function') ? !!shareReady() : null;
      out.label = (typeof CW !== 'undefined' && CW.copied) ? String(CW.copied) : null;
      out.before = (typeof SHARE_BUTTON !== 'undefined' && SHARE_BUTTON)
        ? String(SHARE_BUTTON.textContent) : null;
      press('c');
      step(6);
      setTimeout(function(){
        try {
          out.clip = window.__clip;
          out.after = (typeof SHARE_BUTTON !== 'undefined' && SHARE_BUTTON)
            ? String(SHARE_BUTTON.textContent) : null;
          const facts = (typeof shareFacts === 'function') ? shareFacts() : {};
          out.last = facts.last ? String(facts.last).slice(0, 60) : null;
          out.text = facts.text ? String(facts.text).slice(0, 60) : null;
          out.copies = facts.copies;
        } catch (e) { out.err = String(e).slice(0, 80) }
        document.title = 'SHARECOPY' + JSON.stringify(out);
      }, 400);
    } catch (e) { document.title = 'SHARECOPY' + JSON.stringify({err: String(e).slice(0, 120)}) }
  }, 800);
});
</script>
"""


@dataclass(frozen=True)
class ShareProofResult:
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def read_page() -> dict:
    """Play a round to its end, press the copy key, and watch the clipboard."""

    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        return {"err": "no browser"}
    html = generate_game(ASK).html
    body = with_probe_keys(_REPORT.replace("FRAMES_TOKEN", str(FRAMES)))
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
                "--virtual-time-budget=12000",
                "--window-size=390,844",
                "--dump-dom",
                f"file://{page}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    found = _TITLE.search(run.stdout)
    return json.loads(found.group(1)) if found else {"err": "the page said nothing"}


def evaluate_share_says_copied_only_with_proof() -> ShareProofResult:
    total = 4
    seen = read_page()
    if "err" in seen or not seen.get("ready"):
        return ShareProofResult(0, total, (str(seen.get("err", "the round never ended")),))

    clip = seen.get("clip") or {}
    passed = 0
    failures: list[str] = []

    if clip.get("asked", 0) >= 1:
        passed += 1
    else:
        failures.append("the page never asked the clipboard")
    if clip.get("tried", 0) >= 1:
        passed += 1
    else:
        failures.append("the old trick was never tried, and the promise never settled")

    proof = clip.get("settled", 0) >= 1 or clip.get("trick") is True
    claimed = seen.get("after") == seen.get("label")
    if claimed == proof:
        passed += 1
    elif claimed:
        failures.append(
            f"the button says {seen.get('after')!r} with no proof "
            f"(settled {clip.get('settled')}, trick {clip.get('trick')})"
        )
    else:
        failures.append("the copy worked and the button did not say so")
    if seen.get("last") and seen["last"] == seen.get("text"):
        passed += 1
    else:
        failures.append(f"the line it copied was {seen.get('last')!r}")

    readings = (
        f"asked {clip.get('asked')} / settled {clip.get('settled')} / "
        f"refused {clip.get('refused')} / old trick {clip.get('trick')} / "
        f"button {seen.get('after')!r}",
    )
    return ShareProofResult(passed, total, tuple(failures[:3]), readings)


__all__ = [
    "ASK",
    "FRAMES",
    "ShareProofResult",
    "evaluate_share_says_copied_only_with_proof",
    "read_page",
]
