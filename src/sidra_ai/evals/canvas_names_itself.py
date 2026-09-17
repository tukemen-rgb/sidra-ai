"""Does the canvas tell a reader who cannot see it what is there?

§28, §29 and §30 settled hearing, movement and memory. Nobody had written
down the reader who cannot see the screen at all - and SIDRA's artifacts
are a single `<canvas>` with everything inside it, so this matters here
more than anywhere else.

§36 事実 1 (MDN): content placed INSIDE the canvas element is its fallback
for assistive technology, and a browser that can draw canvas ignores it -
so adding it changes nothing for a sighted viewer. §36 事実 2 (WCAG 1.1.1):
non-text content needs a text alternative, and where the content is a test
or a sensory experience that cannot honestly be turned into prose, the
alternative must still 「provide descriptive identification」.

All three canvases shipped empty, and the existing validators only asked
whether the string 「<canvas」 appeared at all, so an empty one passed.

What is required here is descriptive identification, not a transcript:

  (a) the canvas has fallback content, and it is not only whitespace;
  (b) it names THIS page - the title the page itself carries - so a
      constant like 「ゲームです」 cannot satisfy it;
  (c) it says something beyond the title, because a bare echo of the
      heading tells a reader nothing about what is on the canvas;
  (d) every artifact kind that ships a canvas is checked, so a new kind
      cannot arrive without an alternative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The shortest fallback that can carry an identification: the title, plus
#: a clause saying what is there. Below this it is a label, not a sentence.
MIN_CHARS = 12

#: How much has to be there beyond the page's own title.
MIN_BEYOND_TITLE = 8

_CANVAS = re.compile(r"<canvas[^>]*>(.*?)</canvas>", re.S)
_TAG = re.compile(r"<[^>]+>")


def canvas_alternative(html: str) -> str | None:
    """The text inside the page's first canvas, or None if there is none."""

    found = _CANVAS.search(html)
    if found is None:
        return None
    return _TAG.sub(" ", found.group(1)).strip()


@dataclass(frozen=True)
class CanvasNamesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _kinds() -> dict[str, tuple[str, str]]:
    """Each artifact kind that ships a canvas: its html and its title."""

    from sidra_ai.creation.art import generate_art
    from sidra_ai.creation.games import generate_game
    from sidra_ai.creation.models3d import generate_model3d

    game = generate_game("シューティングゲームを作って")
    art = generate_art("抽象的な絵を作って")
    model = generate_model3d("立方体の 3D モデルを作って")
    return {
        "game": (game.html, game.title),
        "art": (art.html, art.title),
        "model3d": (model.preview_html, model.title),
    }


def evaluate_canvas_names_itself() -> CanvasNamesResult:
    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    kinds = _kinds()
    for kind, (html, title) in sorted(kinds.items()):
        alt = canvas_alternative(html)
        if alt is None:
            failures.append(f"{kind}: the page has no canvas at all")
            continue
        # (a) there is something there
        if len(alt) < MIN_CHARS:
            failures.append(
                f"{kind}: the canvas says {alt!r} - too little to identify anything"
            )
            continue
        checks += 1
        # (b) it is about this page
        if title and title not in alt:
            failures.append(f"{kind}: the alternative never names 「{title}」")
        else:
            checks += 1
        # (c) and says more than the title does
        beyond = len(alt) - len(title or "")
        if beyond < MIN_BEYOND_TITLE:
            failures.append(
                f"{kind}: the alternative is the title and little else ({beyond} chars beyond it)"
            )
        else:
            checks += 1
        readings.append(f"{kind}=「{alt[:34]}…」" if len(alt) > 34 else f"{kind}=「{alt}」")

    # (d) every kind that ships a canvas is here. Read from the source so a
    # fourth one cannot be added without this judge noticing.
    from pathlib import Path

    creation = Path(__file__).resolve().parents[1] / "creation"
    with_canvas = {
        path.stem
        for path in sorted(creation.glob("*.py"))
        if re.search(r"<canvas[^>]*>", path.read_text(encoding="utf-8"))
    }
    covered = {"games": "game", "art": "art", "models3d": "model3d"}
    for module in sorted(with_canvas - set(covered)):
        failures.append(f"{module}.py ships a canvas that nothing here checks")
    if not with_canvas - set(covered):
        checks += 1

    return CanvasNamesResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
