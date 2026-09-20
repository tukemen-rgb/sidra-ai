"""Does the size shown carry to the next unit when rounding reaches 1024?

C-1987, the boundary that C-1895's ``formatBytes`` left open. That fix made the
generated-file listing print ``KB``/``MB`` instead of a raw byte count, and its
eval (``ui_artifact_size_is_human_readable``) pins the *mechanism* - it divides
by 1024, it names the units, both loops call it. What no check reads is the
*value* at the top of a unit.

``formatBytes`` scales while ``value >= 1024`` and then rounds to a whole number
below 10 (``Math.round(value)``). For a size just under a power of 1024 - say
``1048064`` bytes, which is ``1023.5`` KB - the loop stops (``1023.5 < 1024``)
and ``Math.round`` returns ``1024``. The listing then reads ``"1024 KB"`` where
a person expects ``"1.0 MB"``; the same happens at ``"1024 MB"`` a byte below a
gigabyte. On the one surface whose whole question is "how big is what I made",
a unit that fails to carry is a size shown wrong.

Rendered layout cannot be computed offline, so this runs the page's *own*
``formatBytes`` in a real JS engine (node) - the same way
``adapt_panel_easing_matches_actual_ease`` runs the page's preamble - and reads
what it returns for the boundary sizes and for ordinary ones. The boundary
cases must not read ``"1024 <unit>"``; the ordinary ones must be unchanged, so a
fix that promoted too eagerly (turning ``1023 KB`` into ``1.0 MB``) fails here
too.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class UiSizeCarriesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _format_bytes_source(page: str) -> str:
    # From `function formatBytes(` to the next top-level `function ` at the same
    # indentation - the whole helper, so node can call it exactly as the page
    # defines it (the same slice ui_artifact_size_is_human_readable scopes to).
    start = page.find("function formatBytes(")
    if start < 0:
        return ""
    rest = page[start:]
    end = rest.find("\n  function ", len("function formatBytes("))
    return rest if end < 0 else rest[:end]


# (bytes, expected) pairs. The first five are the boundary the bug lives at; the
# rest are ordinary sizes that must not move (over-eager promotion breaks them).
_CASES = (
    (1048064, "1.0 MB"),   # 1023.5 KB -> rounds to 1024 KB on the buggy path
    (1048575, "1.0 MB"),   # one byte under 1 MB
    (1048576, "1.0 MB"),   # exactly 1 MB
    (1073741823, "1.0 GB"),  # one byte under 1 GB -> "1024 MB" on the bug
    (1073741824, "1.0 GB"),  # exactly 1 GB
    (1047552, "1023 KB"),  # 1023.0 KB - must stay KB, not promote
    (1023, "1023 B"),
    (1024, "1.0 KB"),
    (109927, "107 KB"),
    (3201, "3.1 KB"),
    (2411520, "2.3 MB"),
    (0, "0 B"),
)


def _run(page: str) -> list[str]:
    src = (
        _format_bytes_source(page)
        + "\nconst __in = "
        + json.dumps([n for n, _ in _CASES])
        + ";\nconsole.log(JSON.stringify(__in.map(function (n) { return formatBytes(n); })));\n"
    )
    run = subprocess.run(
        ["node", "-"], input=src, capture_output=True, text=True, timeout=120
    )
    if run.returncode != 0:
        raise ValueError(run.stderr.strip()[:200])
    return json.loads(run.stdout.strip().splitlines()[-1])


def evaluate_ui_artifact_size_carries_at_unit_boundary() -> UiSizeCarriesResult:
    from sidra_ai.api.ui import ASK_PAGE

    total = len(_CASES) + 1  # each case, plus a "no 1024 <unit>" guard
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return UiSizeCarriesResult(False, 0, total, ("node is unavailable",))

    body = _format_bytes_source(ASK_PAGE)
    if not body:
        return UiSizeCarriesResult(False, 0, total, ("no formatBytes helper is defined",))

    try:
        got = _run(ASK_PAGE)
    except ValueError as exc:
        return UiSizeCarriesResult(False, 0, total, (f"node run failed: {exc}",))

    checks = 0
    failures: list[str] = []

    for (n, want), have in zip(_CASES, got):
        if have == want:
            checks += 1
        else:
            failures.append(f"{n} -> {have!r}, want {want!r}")

    # The defect in one line: a rounded value of 1024 must never be shown with a
    # unit that had a larger one above it. "1024 TB" is allowed (nothing is
    # bigger); "1024 KB"/"1024 MB"/"1024 GB" are the carry that never happened.
    bad = [g for g in got if g in ("1024 KB", "1024 MB", "1024 GB")]
    if not bad:
        checks += 1
    else:
        failures.append(f"unit failed to carry: {bad}")

    return UiSizeCarriesResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "UiSizeCarriesResult",
    "evaluate_ui_artifact_size_carries_at_unit_boundary",
]
