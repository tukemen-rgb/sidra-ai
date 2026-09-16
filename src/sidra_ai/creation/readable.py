"""Readability floors for the pages the product ships, not just its palettes.

:mod:`sidra_ai.creation.themes` carries ``CONTRAST_FLOORS``: seven
``(foreground token, background token, minimum ratio)`` triples that every
theme in the catalogue has to clear. That rule is real and it works - but it
binds *four palettes*, and nothing else. The four HTML pages this product
writes paint far more than seven combinations, and C-1877 measured the
distance: 21 rules, 69 cells once the themed pages are taken across the
catalogue, of which the token table reached 40 at the right floor.

The twenty-nine it did not reach are not obscure corners:

* ``art.py`` and ``models3d.py`` do not use theme tokens at all. Their honest
  notes - 「依頼にあった色は今の配色に反映していません」, 「依頼にあった題材は
  描いていません」 - are painted in a hard-coded ``#ffb84d`` that no rule over
  tokens can ever see.
* ``decks.py`` paints 「出典なし - この欄は埋まっていません」 in ``alert`` at
  12px. ``alert`` has exactly one floor, ``(alert, surface, 3.0)``, and 3.0 is
  the *non-text* number - the floor for a drawn shape, not for a sentence.
* ``decks.py``'s subject banner and footer, and ``games.py``'s links and
  footer, sit on ``bg``; ``(alert, bg)``, ``(muted, bg)`` and ``(accent, bg)``
  are not pairs the token table has.

Every one of those cells passes today - the worst measured 5.14:1, on the art
page's caption - so this module fixes no visible defect. What it fixes is that
nothing held them there: a repaint, or a fifth theme, would have gone out
green. §4's own re-measurement on 2026-09-14 found the same shape in
``creation_pad_visible`` (12 of 120 cells) and widened it; this is the next
instrument along.

``CONTRAST_FLOORS`` is deliberately left as it is. Raising ``(alert, surface)``
to 4.5 because the deck paints a sentence in it - every theme measures 6.33 or
better, so it would cost nothing - would put the same requirement in two
tables, and two tables that must agree are the drift this module exists to
stop. The floors over the palettes stay about palettes; the floor over a
sentence lives next to the sentence.

The table is one row per selector-and-background, because a colour is only
readable *over something*: ``decks.py``'s body copy is the same ``text`` token
inside a slide and outside it, and those are two different questions. Where a
selector paints text at more than one size - ``small`` and ``li`` share a
declaration in ``models3d.py`` - the row carries the **smallest** size, which
is the one that has to clear the higher floor. Sizes that an element inherits
or gets from a keyword are not guessed: a browser resolves the real pages and
the table has to match it (``tests/test_creation_page_text.py``), which is how
``small`` was corrected from an assumed 12.8 to the 13.3333 the engine gives.

Two rules keep the table from becoming a second, quieter source of truth:

* ``opacity`` is resolved, not ignored. ``art.py`` dims its caption to .6,
  which changes the colour the eye receives after the palette has had its say;
  a floor applied to the declared colour would be measuring a colour nobody
  sees.
* the pages' own ``<style>`` blocks are read back and required to match this
  table, selector for selector (``tests/test_creation_page_text.py``). A table
  that only the judge reads would score full marks the day someone repaints a
  page and forgets it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .themes import THEMES, contrast_ratio

#: WCAG 1.4.3 「large text」: 18pt, or 14pt when bold. At the 16px/1pt=1.333px
#: the CSS pixel gives, that is 24px and 18.66px.
LARGE_PX = 24.0
LARGE_BOLD_PX = 18.66

#: 1.4.3's two numbers. Normal-size text 4.5:1, large text 3.0:1.
NORMAL_FLOOR = 4.5
LARGE_FLOOR = 3.0


def text_floor(px: float, bold: bool = False) -> float:
    """The WCAG 1.4.3 floor a run of text at this size and weight must clear."""

    if px >= LARGE_PX or (bold and px >= LARGE_BOLD_PX):
        return LARGE_FLOOR
    return NORMAL_FLOOR


def over(fg: str, bg: str, alpha: float) -> str:
    """``fg`` at ``alpha`` composited onto ``bg``, as a hex colour.

    The colour a reader receives, which is the only one a contrast floor has
    any business measuring.
    """

    if alpha >= 1.0:
        return fg
    top, under = fg.lstrip("#"), bg.lstrip("#")
    parts = []
    for i in (0, 2, 4):
        mixed = int(top[i : i + 2], 16) * alpha + int(under[i : i + 2], 16) * (1 - alpha)
        parts.append(f"{max(0, min(255, round(mixed))):02x}")
    return "#" + "".join(parts)


@dataclass(frozen=True)
class TextRule:
    """One selector that sets ``color:``, and what it is read against.

    ``fg`` and ``bg`` are either a literal ``#rrggbb`` - the unthemed pages -
    or the name of a theme token. ``px`` is the smallest size the selector
    paints, ``bold`` whether the element is bold by default (``h2``), and
    ``alpha`` the effective ``opacity`` on the text.
    """

    selector: str
    fg: str
    bg: str
    px: float
    bold: bool = False
    alpha: float = 1.0
    note: str = ""

    @property
    def floor(self) -> float:
        return text_floor(self.px, self.bold)


#: The unthemed pages' fixed colours, named so the table reads like the CSS.
_ART_BG = "#05070f"
_ART_CAPTION = "#2ee6ff"
#: The amber both unthemed pages use for their honest notes. Not a theme
#: token, which is precisely why the token table could never reach it.
_NOTE_AMBER = "#ffb84d"
_M3D_BG = "#05070f"
_M3D_TEXT = "#e6f7ff"
_M3D_QUIET = "#8fb3c7"


PAGE_TEXT: dict[str, tuple[TextRule, ...]] = {
    "creation/art.py": (
        TextRule("p", _ART_CAPTION, _ART_BG, 12.0, alpha=0.6,
                 note="caption: 「{title} — seed {n}」"),
        TextRule("p.note", _NOTE_AMBER, _ART_BG, 12.0, alpha=0.85,
                 note="the honest notes (pattern / colour / subject not applied)"),
    ),
    "creation/models3d.py": (
        TextRule("body", _M3D_TEXT, _M3D_BG, 16.0, note="title and body copy"),
        TextRule("#shape-note,#color-note,#count-note", _NOTE_AMBER, _M3D_BG, 14.4,
                 note="the honest notes"),
        TextRule("small,li", _M3D_QUIET, _M3D_BG, 13.3333,
                 note="how-to line and sources; 13.3333 is what the engine "
                      "resolves `small` to on a 16px body - written as 12.8 "
                      "here first, from 0.8em, and corrected by the browser "
                      "check in tests/test_creation_page_text.py"),
    ),
    "creation/decks.py": (
        TextRule("body", "text", "bg", 16.0, note="the deck title"),
        TextRule("body", "text", "surface", 16.0, note="the bullets, inside a slide"),
        TextRule(".slide .no", "muted", "surface", 12.0, note="slide number"),
        TextRule(".slide h2", "accent", "surface", 19.0, bold=True,
                 note="slide heading; h2 is bold, so 19px is large text"),
        TextRule(".slide .src", "muted", "surface", 12.0, note="sources line"),
        TextRule(".slide .blank", "alert", "surface", 12.0,
                 note="「出典なし - この欄は埋まっていません」"),
        TextRule(".subject-miss", "alert", "bg", 13.0,
                 note="the banner saying the named subject is not in the deck"),
        TextRule("footer", "muted", "bg", 12.0),
    ),
    "creation/games.py": (
        TextRule("body", "text", "bg", 16.0, note="title and body copy"),
        TextRule("p.tag", "subtle", "bg", 16.0, note="the one-line description"),
        TextRule(".how", "code", "raised", 13.0, note="how to play"),
        TextRule("footer", "muted", "bg", 12.0),
        TextRule("a", "accent", "bg", 16.0,
                 note="links at body size - not a drawn shape"),
        TextRule(".touchhint", "subtle", "bg", 13.0),
        TextRule(".rotatehint", "subtle", "bg", 13.0),
        TextRule(".fullbtn", "text", "raised", 13.0, note="the fullscreen button's label"),
    ),
}

#: Pages with a ``<style>`` block that are deliberately NOT in the table, and
#: why - the same 「write a reason for the rest」 the storage registry keeps
#: (C-1729). Without this, a missing page and a page judged to need no floor
#: look identical from outside.
UNFLOORED_PAGES: dict[str, str] = {
    "api/ui.py": (
        "色を 1 つも宣言していない（`color-scheme: light dark` と UA 既定のみ）。"
        "前景も背景もブラウザのもので、床を張る相手が無い。"
        "`opacity` だけは自前（.7/.8、無効化ボタンで .5）——実測では "
        "Chromium 既定の上で .7→8.52:1・.8→12.63:1 で余裕があり、"
        ".5 は無効化部品なので WCAG 1.4.3 の対象外。"
        "自前の配色を宣言するかどうかは別の判断で、ここでは覆わない"
    ),
}

#: The pages whose colours come from the theme catalogue, so every cell is
#: judged once per theme.
THEMED_PAGES: tuple[str, ...] = ("creation/decks.py", "creation/games.py")


def resolve(rule: TextRule, tokens: dict[str, str] | None = None) -> tuple[str, str]:
    """``rule``'s effective foreground and background, as hex colours."""

    table = tokens or {}
    fg = table.get(rule.fg, rule.fg)
    bg = table.get(rule.bg, rule.bg)
    return over(fg, bg, rule.alpha), bg


def audit_rule(rule: TextRule, tokens: dict[str, str] | None = None) -> dict:
    """One cell: the ratio a reader gets, and the floor it owes."""

    fg, bg = resolve(rule, tokens)
    ratio = contrast_ratio(fg, bg)
    return {
        "selector": rule.selector,
        "fg": fg,
        "bg": bg,
        "ratio": round(ratio, 2),
        "floor": rule.floor,
        "passed": ratio >= rule.floor,
    }


def audit_page(page: str, theme_key: str | None = None) -> list[dict]:
    """Every cell of one page, under one theme where the page is themed."""

    tokens = THEMES[theme_key].tokens if theme_key else None
    out = []
    for rule in PAGE_TEXT[page]:
        cell = audit_rule(rule, tokens)
        cell["page"] = page
        cell["theme"] = theme_key or "-"
        out.append(cell)
    return out


def audit_all() -> list[dict]:
    """Every cell the product ships: unthemed pages once, themed pages per theme."""

    cells: list[dict] = []
    for page in sorted(PAGE_TEXT):
        if page in THEMED_PAGES:
            for key in sorted(THEMES):
                cells += audit_page(page, key)
        else:
            cells += audit_page(page)
    return cells


__all__ = [
    "LARGE_BOLD_PX",
    "LARGE_PX",
    "NORMAL_FLOOR",
    "LARGE_FLOOR",
    "PAGE_TEXT",
    "THEMED_PAGES",
    "TextRule",
    "UNFLOORED_PAGES",
    "audit_all",
    "audit_page",
    "audit_rule",
    "over",
    "resolve",
    "text_floor",
]
