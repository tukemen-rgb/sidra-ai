"""Is the touch pad's boundary visible on every floor it is drawn over?

§4 増築 (WCAG 1.4.11): a non-text UI component must reach 3:1 against the
colours next to it. The virtual pad is the phone's only control and it sits on
whatever the scene floor is this act, and §7 moves that floor's luminance per
act - so no single ring colour can hold 3:1 everywhere. C-1388's answer is two
concentric rings at the theme's luminance extremes (surface outside, ink
inside, both opaque), which guarantees one of the pair clears the bar on any
floor. This measures that it actually does.

C-1857 is why it lives here. The check ran inside ``product_metrics.py`` on
``template="catch"`` alone - 12 of the 120 cells the rule covers - and found
its floor by the *spelling* ``sky:scenePaint(...)``. adventure and puzzle fill
their canvas with a bare ``fillStyle = scenePaint('#...')``, so widening the
loop without widening the pattern would have reported "no scene floor token"
for two healthy templates: a judge printing zero against a correct product,
which is what ``ui_touch_targets`` had just done to the whole suite the same
afternoon.

Measured before anything was changed: 120 cells, zero failures, worst ring
4.44 - and the worst cell is ``adventure``, one of the two the old pattern
could not read. The product was right; the instrument was looking at a tenth
of it.

The cell count is part of the verdict. Without it the score is blind to its
own sample: the catch-only version scored a clean pass while reading a tenth
of the rule, and narrowing it again would look identical from outside. A judge
that cannot notice it stopped looking is the same defect as a page that cannot
notice it stopped drawing.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.touchpad import pad_probe

#: The four themes, as the request phrases that select them.
THEME_SUFFIXES: tuple[str, ...] = (
    "",
    "紙のテーマで",
    "ターミナルのテーマで",
    "dusk のテーマで",
)

#: Acts per template, from §7's per-scene palettes.
ACTS = 3

#: WCAG 1.4.11's number for non-text contrast.
FLOOR_RATIO = 3.0

#: The full-canvas paint, asked for as an ASSIGNMENT rather than by the key it
#: is assigned to. 「sky:scenePaint(...)」 is one template family's spelling;
#: adventure and puzzle write 「fillStyle = scenePaint(...)」 and were invisible
#: to a pattern that wanted the key (C-1857).
#: 「=」 or 「:」 - an assignment or a key. Written as 「=」 alone at first, which
#: still reached 120 cells because every page happens to carry a
#: 「fillStyle = scenePaint(...)」 somewhere too - so the sweep looked complete
#: while the pattern did not actually handle the spelling this item is about.
#: The test that feeds it both spellings is what caught that.
_FLOOR = re.compile(r"[=:]\s*scenePaint\('(#[0-9a-f]{6})'\)")
_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)


@dataclass(frozen=True)
class PadVisibleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    cells: int = 0
    worst_ring: float = 0.0
    worst_cell: str = ""


def _luminance(colour: str) -> float:
    raw = colour.lstrip("#")
    parts = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _blend(alpha: float, over: str, under: str) -> str:
    o, u = over.lstrip("#"), under.lstrip("#")
    out = []
    for i in (0, 2, 4):
        mixed = int(o[i : i + 2], 16) * alpha + int(u[i : i + 2], 16) * (1 - alpha)
        out.append(f"{max(0, min(255, round(mixed))):02x}")
    return "#" + "".join(out)


def evaluate_pad_visible_every_floor() -> PadVisibleResult:
    checks = 0
    failures: list[str] = []
    cells = 0
    worst = (99.0, "")

    for template in sorted(TEMPLATES):
        for suffix in THEME_SUFFIXES:
            label = f"{template}/{suffix or 'default'}"
            page = generate_game(
                f"ゲームを作って {suffix}".strip(), template=template
            ).html
            script = _SCRIPT.search(page)
            if script is None:
                failures.append(f"{label}: no script")
                continue
            floor_token = _FLOOR.search(script.group(1))
            if floor_token is None:
                # Reported, never skipped: a cell nobody measured must not
                # read as a cell that passed.
                failures.append(f"{label}: no scene floor token")
                continue
            try:
                run = subprocess.run(
                    ["node", "-"],
                    input=pad_probe(
                        script.group(1), floor_token=floor_token.group(1)
                    ),
                    capture_output=True,
                    text=True,
                    timeout=240,
                )
                if run.returncode != 0:
                    raise ValueError(run.stderr.strip()[:60])
                probed = json.loads(run.stdout.strip().splitlines()[-1])
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                failures.append(f"{label}: probe unavailable ({exc})")
                continue
            facts = probed.get("facts") or {}
            for act, under in enumerate(probed.get("floors") or []):
                if not under:
                    failures.append(f"{label}: act {act} floor unread")
                    continue
                cells += 1
                ring = max(
                    _ratio(facts["ringIn"], under), _ratio(facts["ringOut"], under)
                )
                if ring < worst[0]:
                    worst = (ring, f"{label}/act{act}")
                if ring < FLOOR_RATIO:
                    failures.append(
                        f"{label}: act {act} the boundary melts ({ring:.2f})"
                    )
                else:
                    checks += 1
                glyph = _ratio(
                    facts["glyph"], _blend(facts["alpha"], facts["plate"], under)
                )
                if glyph < FLOOR_RATIO:
                    failures.append(
                        f"{label}: act {act} the glyph sinks ({glyph:.2f})"
                    )
                else:
                    checks += 1

    want = len(TEMPLATES) * len(THEME_SUFFIXES) * ACTS
    if cells == want:
        checks += 1
    else:
        failures.append(
            f"judged {cells} of {want} cells "
            f"({len(TEMPLATES)} templates x {len(THEME_SUFFIXES)} themes x {ACTS} acts)"
        )

    return PadVisibleResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
        cells=cells,
        worst_ring=0.0 if worst[1] == "" else worst[0],
        worst_cell=worst[1],
    )
