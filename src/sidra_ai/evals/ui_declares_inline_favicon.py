"""Does the ask page declare its own inline favicon, so the browser stops 404ing?

C-1260: opening the page logged a console error on every load - the browser
auto-requested ``/favicon.ico`` and got a 404 - and the tab showed a blank
icon. The page is deliberately self-contained (loopback only, no CORS, nothing
fetched from another host), so the icon has to be declared inline rather than
served or linked externally: a ``<link rel="icon">`` with a ``data:`` URI. With
it present the browser uses the declared icon and never requests
``/favicon.ico``.

The checks read the served page string: an icon link is present, its href is an
inline ``data:`` URI, and it points at no external host - the same constraint
the rest of the page lives under.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The <link ... rel="icon" ...> tag, however the attributes are ordered.
_ICON_LINK = re.compile(r"<link\b[^>]*\brel=\"[^\"]*icon[^\"]*\"[^>]*>", re.IGNORECASE)
_HREF = re.compile(r"\bhref=\"([^\"]*)\"", re.IGNORECASE)


@dataclass(frozen=True)
class UiInlineFaviconResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_declares_inline_favicon() -> UiInlineFaviconResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    link_match = _ICON_LINK.search(ASK_PAGE)
    # 1: the page declares an icon at all - this is what stops the /favicon.ico
    # request and the 404 with it.
    add(link_match is not None, "no <link rel=\"icon\"> in the page")

    link = link_match.group(0) if link_match else ""
    href_match = _HREF.search(link)
    href = href_match.group(1) if href_match else ""
    # 2: the icon is inline (a data: URI), honoring the page's rule that it
    # fetches nothing from another host.
    add(href.startswith("data:"), f"icon href is not an inline data: URI: {href[:40]!r}")
    # 3: and it names no external host - not http(s):// and not a //host form.
    external = href.startswith("http://") or href.startswith("https://") or href.startswith("//")
    add(link != "" and not external, "icon href points at an external host")

    return UiInlineFaviconResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=3,
        failures=tuple(failures),
    )


__all__ = ["UiInlineFaviconResult", "evaluate_ui_declares_inline_favicon"]
