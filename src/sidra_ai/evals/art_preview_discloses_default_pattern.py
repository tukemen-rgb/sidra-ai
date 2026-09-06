"""Does the generated art page disclose the flow default it fell back to?

C-1284 (the art twin of C-1283): a request that names no pattern (「猫のアート」)
is drawn with the flow default. The chat summary says so (C-1271), but the HTML
is the artifact opened in a browser and forwarded, and it was titled 「猫」 over a
flow drawing with no word of it - the silent artifact C-1281/C-1283 fixed for the
report and the 3D preview. The page now carries a disclosure note under the
caption when the pattern was a default, and stays clean when one was named.

Drives the router's art generator for the saved file and ``generate_art`` for the
property.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

_NOTE_MARK = '<p class="note">'
_PATTERNS = ("フロー", "軌道")


@dataclass(frozen=True)
class ArtPreviewResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _router_html(request: str) -> str:
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.router import build_default_router

    tmp = tempfile.mkdtemp(prefix="art-preview-")
    router = build_default_router(data_dir=tmp)
    out = router.route(request, detect_creation_intent(request), [])
    return Path(out.artifact_path).read_text(encoding="utf-8")


def evaluate_art_preview_discloses_default_pattern() -> ArtPreviewResult:
    from sidra_ai.creation.art import generate_art, validate_art

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 1: the saved page for a no-pattern request discloses the flow default,
    #    names the patterns that can be asked for, and keeps the subject title.
    html = _router_html("猫のアートを作って")
    add(_NOTE_MARK in html, "fallback art page has no disclosure note element")
    add("既定の「フロー」" in html, "fallback art page does not name the flow default")
    add(all(p in html for p in _PATTERNS), "fallback art page omits the pattern choices")
    add("<title>猫</title>" in html, "fallback art page dropped the subject title")

    # 2: a named pattern gets no note (a matched word or an explicit pattern=).
    for req, pattern in (("波のアートを作って", "flow"),
                         ("軌道のアートを作って", "orbits")):
        art = generate_art(req)
        add(art.pattern == pattern and art.pattern_named
            and _NOTE_MARK not in art.html,
            f"named pattern {pattern!r} page should carry no note")

    # 3: the note carries no fabricated figure. Guarded so pre-fix code (no note)
    #    scores a failure rather than crashing.
    fallback = generate_art("犬のアートを作って")
    if _NOTE_MARK in fallback.html:
        note = fallback.html.split(_NOTE_MARK, 1)[1].split("</p>", 1)[0]
        add(not any(ch.isdigit() for ch in note),
            f"disclosure note carries a digit: {note!r}")
    else:
        failures.append("fallback art page has no note to check for a digit")

    # 4: the disclosure does not break the page - it still passes validate_art
    #    (seeded draw, seed in the page, no Math.random).
    add(validate_art(fallback)["valid"], "disclosure made the art page invalid")

    total = 4 + 2 + 1 + 1
    return ArtPreviewResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ArtPreviewResult",
    "evaluate_art_preview_discloses_default_pattern",
]
