"""Read a generated page's *resolved* style out of a real browser engine.

C-1535 asked for this by name: 「判定器は生成ページの canvas/pad 要素に解決された
計算値を見ること」. Grepping the HTML for ``touch-action`` would pass a page that
wrote the rule somewhere it does not apply - a selector matching nothing, a
declaration a later rule overrides, a property inside a media query that never
matches. The only thing that settles it is the cascade, and the cascade is what
a browser has.

There is a Chromium in this environment but no driver binding, so the page is
asked to answer for itself: a read-only script is appended AFTER the page's own
content, it calls ``getComputedStyle`` on the elements named, and writes the
result into one element that ``--dump-dom`` prints back. Nothing in the page's
own markup, style or script is modified, so what the engine resolves is what
the artifact ships with.

When no Chromium is found this returns ``None`` rather than raising or
guessing. A judge that cannot run says so - a missing browser is not evidence
that a page is correct, and it is not a reason to fail a build on a machine
that never promised one.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

#: Where the browsers live in this environment, newest layout first. The
#: executable is looked up rather than assumed so that a machine without one
#: reports "no browser" instead of dying on a missing path.
_CANDIDATES: tuple[str, ...] = (
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
)

_PROBE_ID = "sidra-computed-probe"


def chromium_path() -> str | None:
    """The browser this machine has, or ``None``."""

    env = os.environ.get("SIDRA_CHROMIUM")
    if env and Path(env).exists():
        return env
    for path in _CANDIDATES:
        if Path(path).exists():
            return path
    for root in (Path("/opt/pw-browsers"),):
        if not root.is_dir():
            continue
        for found in sorted(root.glob("chromium*/chrome-linux/chrome")):
            return str(found)
    return None


def computed_styles(
    html: str,
    targets: dict[str, str],
    properties: tuple[str, ...],
    *,
    timeout: int = 120,
) -> dict[str, dict[str, str]] | None:
    """Resolved values for each target, as the engine computes them.

    ``targets`` maps a name to a CSS selector; the result maps the same name to
    ``{property: value}``. A selector that matches nothing comes back as an
    empty dict for that name - which is itself a finding, and the reason the
    caller is told rather than given a default.
    """

    browser = chromium_path()
    if browser is None:
        return None

    reader = (
        "<script>(function(){var out={};var t="
        + json.dumps(targets)
        + ";var props="
        + json.dumps(list(properties))
        + ";for(var k in t){var el=document.querySelector(t[k]);"
        "if(!el){out[k]={};continue}var cs=getComputedStyle(el);var got={};"
        "for(var i=0;i<props.length;i++){var p=props[i];"
        "got[p]=cs.getPropertyValue(p)||cs[p]||''}out[k]=got}"
        "var d=document.createElement('div');d.id=" + json.dumps(_PROBE_ID) + ";"
        "d.textContent=JSON.stringify(out);document.body.appendChild(d)})()</script>"
    )
    # After everything the page ships, so the cascade is already settled.
    page = html + reader

    with tempfile.TemporaryDirectory() as home:
        target = Path(home) / "page.html"
        target.write_text(page, encoding="utf-8")
        try:
            run = subprocess.run(
                [
                    browser,
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    f"--user-data-dir={home}/profile",
                    "--dump-dom",
                    target.as_uri(),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None
    if run.returncode != 0:
        return None
    found = re.search(
        rf'id="{_PROBE_ID}">(.*?)</div>', run.stdout, re.S
    )
    if found is None:
        return None
    try:
        return json.loads(found.group(1))
    except ValueError:
        return None


__all__ = ["chromium_path", "computed_styles"]
