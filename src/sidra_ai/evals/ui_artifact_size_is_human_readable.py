"""Does the entry page show a file's size in units a person reads?

C-1895: the generated-file listing is the only window a general user has onto
what they made, and it printed the size as a raw byte count -
``a.bytes + " bytes"`` for a flat artifact and ``f.bytes + " bytes"`` for a file
inside a production. A 107 KB animation read as ``109927 bytes`` and a 2.3 MB
deck as ``2411520 bytes``; neither is a size anyone parses at a glance, and this
is the one surface where "how big is what I made" is the whole question.

The fix adds one ``formatBytes`` helper and uses it in both render loops, so the
size shows as ``B``/``KB``/``MB``. Rendered layout cannot be computed offline,
so the checks pin the mechanism on the page source the way ``ui_artifact_list_
bounded`` pins the cap: the helper exists, it divides by 1024 and names the
scaled units, both loops call it, and the raw ``.bytes + " bytes"`` concatenation
is gone from each. The behavioural proof - that ``formatBytes`` maps
109927 -> "107 KB", 3201 -> "3.1 KB", 2411520 -> "2.3 MB" in a real engine -
runs at fix time and is recorded in the loop log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UiArtifactSizeHumanReadableResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _format_bytes_body(page: str) -> str:
    # The body from `function formatBytes(` to the next top-level `function ` at
    # the same indentation - enough to scope the mechanism checks to the helper.
    start = page.find("function formatBytes(")
    if start < 0:
        return ""
    rest = page[start:]
    end = rest.find("\n  function ", len("function formatBytes("))
    return rest if end < 0 else rest[:end]


def evaluate_ui_artifact_size_is_human_readable() -> UiArtifactSizeHumanReadableResult:
    from sidra_ai.api.ui import ASK_PAGE

    body = _format_bytes_body(ASK_PAGE)

    checks = 0
    failures: list[str] = []

    # 1: a size-formatting helper exists at all.
    if body:
        checks += 1
    else:
        failures.append("no formatBytes helper is defined")

    # 2: it actually scales - divides by 1024 - rather than printing the raw
    # count under a new name. A gutted body that just returns the number fails
    # here even though check 1 still sees the function.
    if re.search(r"/=?\s*1024", body):
        checks += 1
    else:
        failures.append("formatBytes does not divide by 1024 (no scaling)")

    # 3 and 4: it names the scaled units, so the output is a size and not bytes
    # with a different label. Both KB and MB, so a MB-sized file is not printed
    # as thousands of KB.
    if '"KB"' in body or "'KB'" in body:
        checks += 1
    else:
        failures.append("formatBytes does not name KB")
    if '"MB"' in body or "'MB'" in body:
        checks += 1
    else:
        failures.append("formatBytes does not name MB")

    # 5: the flat-artifact listing routes its size through the helper.
    if re.search(r"formatBytes\(\s*a\.bytes\s*\)", ASK_PAGE):
        checks += 1
    else:
        failures.append("the artifact list does not call formatBytes(a.bytes)")

    # 6: the per-production file listing routes its size through the helper too -
    # the second place the raw count showed.
    if re.search(r"formatBytes\(\s*f\.bytes\s*\)", ASK_PAGE):
        checks += 1
    else:
        failures.append("the project file list does not call formatBytes(f.bytes)")

    # 7 and 8: the raw concatenation is gone from each loop, so a size cannot
    # regress to bytes while the helper sits unused beside it. The guard is the
    # concatenation start (no trailing quote) because the flat listing appended
    # `` + " bytes / " + a.modified`` while the project one closed the string -
    # both begin ``X.bytes + " bytes``.
    if 'a.bytes + " bytes' not in ASK_PAGE:
        checks += 1
    else:
        failures.append('the artifact list still shows a.bytes + " bytes"')
    if 'f.bytes + " bytes' not in ASK_PAGE:
        checks += 1
    else:
        failures.append('the project file list still shows f.bytes + " bytes"')

    return UiArtifactSizeHumanReadableResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=8,
        failures=tuple(failures),
    )


__all__ = [
    "UiArtifactSizeHumanReadableResult",
    "evaluate_ui_artifact_size_is_human_readable",
]
