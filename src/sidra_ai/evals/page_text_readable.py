"""Does every sentence the shipped pages paint clear its WCAG floor - and is
anything holding it there?

§4's quantified rule is WCAG 1.4.3: normal-size text 4.5:1 against its
background, large text 3.0:1. The product has carried that rule since C-1329,
but only in one place - ``themes.CONTRAST_FLOORS``, seven token pairs, checked
against the four palettes and nothing else. C-1877 measured what the pages
actually paint: 21 rules over 4 HTML surfaces, 69 cells once the themed pages
are taken across the catalogue. **The token table reached 40 of them at the
right floor.**

The 29 it missed are the ones a reviewer would pick out first: the honest
notes on the art and 3D pages (a hard-coded ``#ffb84d``, not a token at all),
the deck's 「出典なし - この欄は埋まっていません」 (``alert`` at 12px, whose
only floor was the 3.0 meant for drawn shapes), the deck's subject banner and
both footers and the game page's links (all on ``bg``, a background the token
table has no pair for).

Every cell passes today; the tightest is 5.14:1 on the art page's caption,
which is dimmed to ``opacity:.6``. So this judge is not reporting a broken
product. It is closing the gap §4 itself found in ``creation_pad_visible`` on
2026-09-14 - an instrument reading a tenth of its own rule - one instrument
along.

Three things are measured, and the third is what makes the first two worth
anything:

1. **every cell clears its floor**, with ``opacity`` composited first, because
   a floor applied to a colour the reader never receives measures nothing;
2. **the cell count is part of the verdict** - a judge that quietly stops
   looking scores the same as a page that quietly stops drawing;
3. **the table matches the pages**. Each page's ``<style>`` is read back and
   its ``color:``-setting selectors - and the colour and the ``opacity`` each
   one declares - must be exactly the table's. Without this the whole thing is
   one-sided: emptying ``PAGE_TEXT`` would score full marks, and so would
   repainting a page and forgetting the table. Selectors alone were not
   enough either; a page can be repainted without renaming anything.

A page that declares no colours of its own is not silently skipped either: it
has to be named in ``UNFLOORED_PAGES`` with a reason (``api/ui.py`` is, and
the reason is measured). A new page with a ``<style>`` block and no entry
anywhere is a failure, not an absence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.creation.art import generate_art
from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.creation.readable import (
    PAGE_TEXT,
    THEMED_PAGES,
    UNFLOORED_PAGES,
    audit_page,
)
from sidra_ai.creation.themes import DEFAULT_THEME, THEMES

_STYLE = re.compile(r"<style>(.*?)</style>", re.S)
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
#: ``color:`` as its own property. ``background-color`` is ruled out by what
#: may precede the word and ``color-scheme`` by what must follow it - and the
#: lookbehind rather than a leading delimiter because the first declaration in
#: a block has no delimiter in front of it at all. Written as 「(^|[;\s])」
#: first, and D4 of C-1877's destruction run walked straight through it: a
#: page spelled 「p{color:#445566}」 was invisible to the scan that is supposed
#: to notice a page with no floor. Every shipped page happens to put a space
#: or a semicolon there, so the check looked complete while missing the one
#: spelling it existed to catch - the same shape as C-1857's 「sky:scenePaint」.
_COLOUR = re.compile(r"(?<![-\w])color\s*:")
_COLOUR_VALUE = re.compile(r"(?<![-\w])color\s*:([^;}]+)")
_OPACITY_VALUE = re.compile(r"(?:^|[;\s])opacity\s*:\s*([0-9.]+)")


@dataclass(frozen=True)
class PageTextResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    cells: int = 0
    worst_ratio: float = 0.0
    worst_cell: str = ""


def _pages() -> dict[str, str]:
    """One real page from each shipped HTML surface, built by its own maker.

    Themed pages are built once: the palette is substituted into the same
    stylesheet whatever the theme, so the CSS shape is theme-independent and
    the per-theme question is answered from the token table instead.
    """

    return {
        "creation/art.py": generate_art("絵を作って").html,
        "creation/models3d.py": generate_model3d("3D モデルを作って").preview_html,
        "creation/decks.py": generate_deck("デッキを作って").html,
        "creation/games.py": generate_game("ゲームを作って", template="racing").html,
    }


def colour_selectors(html: str) -> dict[str, tuple[str, float | None]]:
    """Every selector in a page's ``<style>`` that sets ``color:``, with the
    colour it sets and the ``opacity`` declared beside it.

    The value, not only the name. Comparing selector lists alone would let a
    page be repainted to anything at all - the table would still recognise the
    selector and go on scoring the old colour, which is the shape of check
    this session has had to unpick a dozen times.
    """

    style = _STYLE.search(html)
    if style is None:
        return {}
    css = _COMMENT.sub("", style.group(1))
    found: dict[str, tuple[str, float | None]] = {}
    for selector, body in _RULE.findall(css):
        colour = _COLOUR_VALUE.search(body)
        if colour is None:
            continue
        alpha = _OPACITY_VALUE.search(body)
        found[" ".join(selector.split())] = (
            colour.group(1).strip().lower(),
            float(alpha.group(1)) if alpha else None,
        )
    return found


#: A stylesheet in a module's own source, so the scan below reads what a page
#: is built from rather than what a module happens to mention. The instruments
#: that pick a page apart carry ``<style>(.*?)</style>`` as a pattern; none of
#: them paints anything.
_STYLE_SPAN = re.compile(r"<style>(.*?)</style>", re.S)
#: ``color:`` as a DECLARATION - opening a block or following a semicolon.
#: Prose about the property (this file is full of it) mentions the word
#: without ever putting it after a 「{」 or a 「;」, and this module's own
#: docstring is what proved that the plain word was not enough: with
#: ``<style>`` written in the prose above and ``</style>`` in the pattern
#: below, the span this scan read was several paragraphs of English, and the
#: judge reported its own source file as an unfloored page.
_DECLARED_COLOUR = re.compile(r"[;{]\s*color\s*:")


def styled_modules(root: Path | None = None) -> set[str]:
    """Every module that writes a stylesheet that paints text, by its path
    under ``sidra_ai/``.

    Scanned rather than listed, so a new page cannot join the product without
    either a floor or a written reason for having none.
    """

    base = root or Path(__file__).resolve().parents[1]
    out = set()
    for path in sorted(base.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if any(_DECLARED_COLOUR.search(span) for span in _STYLE_SPAN.findall(source)):
            out.add(str(path.relative_to(base)))
    return out


def evaluate_page_text_readable() -> PageTextResult:
    checks = 0
    failures: list[str] = []
    cells = 0
    worst = (99.0, "")

    # 1. every cell clears its floor.
    for page in sorted(PAGE_TEXT):
        keys = sorted(THEMES) if page in THEMED_PAGES else [None]
        for key in keys:
            for cell in audit_page(page, key):
                cells += 1
                where = f"{page}/{cell['theme']}/{cell['selector']}"
                if cell["ratio"] < worst[0]:
                    worst = (cell["ratio"], where)
                if cell["passed"]:
                    checks += 1
                else:
                    failures.append(
                        f"{where}: {cell['ratio']:.2f} < {cell['floor']}"
                    )

    want = sum(
        len(rules) * (len(THEMES) if page in THEMED_PAGES else 1)
        for page, rules in PAGE_TEXT.items()
    )
    if cells == want:
        checks += 1
    else:
        failures.append(f"judged {cells} of {want} cells")

    # 2. the table still describes the pages it claims to describe - the
    #    selectors AND what they are painted with. The pages here are built
    #    with the default theme, so that is the palette the declared tokens
    #    are resolved through.
    for page, html in _pages().items():
        painted = colour_selectors(html)
        rules = PAGE_TEXT[page]
        declared = {rule.selector for rule in rules}
        # Reported both ways round: a selector the page paints and the table
        # has forgotten is an unjudged sentence; a selector the table keeps
        # and the page no longer paints is a cell scoring marks for nothing.
        for extra in sorted(set(painted) - declared):
            failures.append(f"{page}: 「{extra}」 is painted and unfloored")
        for stale in sorted(declared - set(painted)):
            failures.append(f"{page}: 「{stale}」 is floored and unpainted")
        if set(painted) == declared:
            checks += 1

        tokens = DEFAULT_THEME.tokens if page in THEMED_PAGES else {}
        for rule in rules:
            seen = painted.get(rule.selector)
            if seen is None:
                continue
            want = tokens.get(rule.fg, rule.fg).lower()
            if seen[0] != want:
                failures.append(
                    f"{page}: 「{rule.selector}」 paints {seen[0]}, floored as {want}"
                )
            elif seen[1] is not None and abs(seen[1] - rule.alpha) > 1e-9:
                failures.append(
                    f"{page}: 「{rule.selector}」 is dimmed to {seen[1]}, "
                    f"floored at {rule.alpha}"
                )
            else:
                checks += 1

    # 3. no page with a stylesheet is simply absent.
    for module in sorted(styled_modules()):
        if module in PAGE_TEXT or module in UNFLOORED_PAGES:
            checks += 1
        else:
            failures.append(f"{module}: has a <style> block and no floor, no reason")

    return PageTextResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
        cells=cells,
        worst_ratio=0.0 if worst[1] == "" else worst[0],
        worst_cell=worst[1],
    )


__all__ = [
    "PageTextResult",
    "colour_selectors",
    "evaluate_page_text_readable",
    "styled_modules",
]
