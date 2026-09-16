"""The floors under the text on every page this product ships (C-1877).

``themes.CONTRAST_FLOORS`` binds four palettes. These bind the pages: the 21
rules that set ``color:`` across ``art.py``, ``models3d.py``, ``decks.py`` and
``games.py``, judged at WCAG 1.4.3's own numbers with ``opacity`` composited
first.

The last test in this file is the one that makes the rest honest. A table of
sizes and weights written by hand is a claim about what a browser will do, and
the browser is right here: Chromium resolves the real pages and the table has
to agree with it. Without that, ``.slide h2`` could be called bold - and let
off with the 3.0 large-text floor - purely because this file said so.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.browser import chromium_path, computed_styles
from sidra_ai.creation.art import generate_art
from sidra_ai.creation.decks import Fact, generate_deck
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.creation.readable import (
    LARGE_BOLD_PX,
    LARGE_FLOOR,
    LARGE_PX,
    NORMAL_FLOOR,
    PAGE_TEXT,
    THEMED_PAGES,
    UNFLOORED_PAGES,
    audit_all,
    over,
    text_floor,
)
from sidra_ai.creation.themes import THEMES, contrast_ratio
from sidra_ai.evals.page_text_readable import (
    colour_selectors,
    evaluate_page_text_readable,
    styled_modules,
)


def test_text_floor_is_wcag_1_4_3_not_a_rounder_number() -> None:
    assert text_floor(16.0) == NORMAL_FLOOR
    assert text_floor(LARGE_PX) == LARGE_FLOOR
    assert text_floor(LARGE_PX - 0.1) == NORMAL_FLOOR
    # 14pt bold is large; 14pt plain is not. The deck's 19px headings live
    # exactly in that gap, so the weight is load-bearing.
    assert text_floor(LARGE_BOLD_PX, bold=True) == LARGE_FLOOR
    assert text_floor(LARGE_BOLD_PX - 0.1, bold=True) == NORMAL_FLOOR
    assert text_floor(19.0, bold=False) == NORMAL_FLOOR


def test_opacity_is_resolved_into_the_colour_a_reader_receives() -> None:
    """The art page's caption, which is the tightest cell in the product."""

    dimmed = over("#2ee6ff", "#05070f", 0.6)
    assert dimmed == "#1e8d9f"
    assert dimmed != "#2ee6ff"
    # 13.30 undimmed, 5.14 as drawn. A floor applied to the declared colour
    # would have been measuring a colour nobody sees.
    assert contrast_ratio("#2ee6ff", "#05070f") == pytest.approx(13.30, abs=0.01)
    assert contrast_ratio(dimmed, "#05070f") == pytest.approx(5.14, abs=0.01)
    assert over("#2ee6ff", "#05070f", 1.0) == "#2ee6ff"


def test_every_cell_the_product_paints_clears_its_floor() -> None:
    cells = audit_all()
    assert len(cells) == 69, "21 rules; the two themed pages are judged per theme"
    bad = [c for c in cells if not c["passed"]]
    assert bad == []


def test_the_judge_is_green_and_says_how_much_it_looked_at() -> None:
    result = evaluate_page_text_readable()
    assert result.failures == ()
    assert result.passed
    assert result.cells == 69
    assert result.checks_total == result.checks_passed + len(result.failures)
    assert result.worst_ratio == pytest.approx(5.14, abs=0.01)
    assert result.worst_cell == "creation/art.py/-/p"


def test_every_styled_page_has_a_floor_or_a_written_reason() -> None:
    found = styled_modules()
    assert found == set(PAGE_TEXT) | set(UNFLOORED_PAGES)
    assert set(PAGE_TEXT) & set(UNFLOORED_PAGES) == set()
    # A reason, not a placeholder: the point of the second table is that
    # 「no floor」 has to be argued for in words.
    for page, reason in UNFLOORED_PAGES.items():
        assert len(reason) > 40, page


def test_a_colour_declaration_is_found_however_it_is_spelled() -> None:
    """D4 of C-1877's destruction run walked through the first pattern here.

    Every shipped page happens to put a space or a semicolon before its
    ``color:``; a page spelled ``p{color:#445566}`` did not, and the scan that
    exists to notice an unfloored page could not see it.
    """

    page = "<style>p{color:#445566}\nb { color: #123456 }\n</style>"
    assert colour_selectors(page) == {
        "p": ("#445566", None),
        "b": ("#123456", None),
    }
    # And the two properties that merely contain the word are not it.
    assert colour_selectors("<style>i{background-color:#fff}</style>") == {}
    assert colour_selectors("<style>:root{color-scheme:dark}</style>") == {}


def test_the_table_carries_the_colour_the_page_actually_paints() -> None:
    """Selector names alone would let a page be repainted to anything."""

    painted = colour_selectors(generate_art("絵を作って").html)
    assert painted["p"] == ("#2ee6ff", 0.6)
    assert painted["p.note"] == ("#ffb84d", 0.85)


def test_the_honest_notes_are_floored_as_text_not_as_shapes() -> None:
    """The sentences this item exists for.

    ``alert`` and the amber notes carry 「出典なし」, 「依頼にあった色は今の配色に
    反映していません」 and the deck's subject banner. Before C-1877 the only
    floor over ``alert`` was 3.0 - the number WCAG 1.4.11 sets for a drawn
    shape - and the amber was not a theme token at all.
    """

    rows = {
        (page, rule.selector): rule
        for page, rules in PAGE_TEXT.items()
        for rule in rules
    }
    for key in (
        ("creation/decks.py", ".slide .blank"),
        ("creation/decks.py", ".subject-miss"),
        ("creation/art.py", "p.note"),
        ("creation/models3d.py", "#shape-note,#color-note,#count-note"),
    ):
        assert rows[key].floor == NORMAL_FLOOR, key

    for theme in THEMES.values():
        tokens = theme.tokens
        assert contrast_ratio(tokens["alert"], tokens["bg"]) >= NORMAL_FLOOR
        assert contrast_ratio(tokens["alert"], tokens["surface"]) >= NORMAL_FLOOR


def test_the_themed_pages_are_the_ones_that_use_tokens() -> None:
    for page, rules in PAGE_TEXT.items():
        literal = [r for r in rules if r.fg.startswith("#") or r.bg.startswith("#")]
        if page in THEMED_PAGES:
            assert literal == [], page
        else:
            assert len(literal) == len(rules), page


#: What the table claims, and the element on a real page that answers for it.
#: Facts that answer the outline's cues and mention nothing about the subject
#: - which is what raises the deck's subject banner (C-1846).
_OFF_SUBJECT_FACTS = [
    Fact("背景と目的をまとめる。", "docs/a.md"),
    Fact("課題は納期である。", "docs/b.md"),
    Fact("対策は自動化である。", "docs/c.md"),
    Fact("まとめとして効果を示す。", "docs/d.md"),
]


#: ``a`` is deliberately absent: ``games.py`` styles links, but no page this
#: product writes renders an ``<a>``. That row is a floor set in advance, and
#: there is nothing for a browser to resolve.
#:
#: The deck is built from facts that do not mention its subject, because that
#: is the only deck that carries all three of the lines this item is about:
#: the subject banner, a filled source line, and an empty one. A deck asked
#: for with no facts at all shows 「出典なし」 on every slide and no banner,
#: so ``.slide .src`` and ``.subject-miss`` would have had nothing to answer
#: for - a browser check that quietly skips the cells it exists to confirm.
_BROWSER_CELLS: tuple[tuple[str, str, str, float, bool, float], ...] = (
    ("art", "p", "rgb(46, 230, 255)", 12.0, False, 0.6),
    ("art", "p.note", "rgb(255, 184, 77)", 12.0, False, 0.85),
    ("deck", "body", "rgb(223, 231, 245)", 16.0, False, 1.0),
    ("deck", ".slide .no", "rgb(125, 142, 166)", 12.0, False, 1.0),
    ("deck", ".slide h2", "rgb(46, 230, 255)", 19.0, True, 1.0),
    ("deck", ".slide .src:not(.blank)", "rgb(125, 142, 166)", 12.0, False, 1.0),
    ("deck", ".slide .src.blank", "rgb(255, 92, 200)", 12.0, False, 1.0),
    ("deck", ".subject-miss", "rgb(255, 92, 200)", 13.0, False, 1.0),
    ("deck", "footer", "rgb(125, 142, 166)", 12.0, False, 1.0),
    ("game", "body", "rgb(223, 231, 245)", 16.0, False, 1.0),
    ("game", "p.tag", "rgb(159, 176, 200)", 16.0, False, 1.0),
    ("game", ".how", "rgb(195, 210, 230)", 13.0, False, 1.0),
    ("game", "footer", "rgb(125, 142, 166)", 12.0, False, 1.0),
    ("game", ".touchhint", "rgb(159, 176, 200)", 13.0, False, 1.0),
    ("game", ".rotatehint", "rgb(159, 176, 200)", 13.0, False, 1.0),
    ("game", ".fullbtn", "rgb(223, 231, 245)", 13.0, False, 1.0),
    ("m3d", "body", "rgb(230, 247, 255)", 16.0, False, 1.0),
    ("m3d", "#shape-note", "rgb(255, 184, 77)", 14.4, False, 1.0),
    ("m3d", "small", "rgb(143, 179, 199)", 13.3333, False, 1.0),
    ("m3d", "li", "rgb(143, 179, 199)", 16.0, False, 1.0),
)


@pytest.mark.skipif(chromium_path() is None, reason="no browser on this machine")
def test_a_real_browser_agrees_with_the_table() -> None:
    """Sizes and weights are inherited; only an engine knows what they land on.

    The CSS-text check in the judge reads declarations, so it cannot see that
    ``p.note`` gets its 12px from ``p``, that ``small`` is 0.8em of a 16px
    body, or that ``h2`` is bold without anyone saying so - the three facts
    that decide which floor those cells owe.
    """

    pages = {
        "art": generate_art("絵を作って").html,
        "deck": generate_deck("犬のデッキを作って", facts=_OFF_SUBJECT_FACTS).html,
        "game": generate_game("ゲームを作って", template="racing").html,
        "m3d": generate_model3d("3D モデルを作って").preview_html,
    }
    wanted: dict[str, dict[str, str]] = {}
    for page, selector, _c, _p, _b, _a in _BROWSER_CELLS:
        wanted.setdefault(page, {})[selector] = selector

    for page, targets in wanted.items():
        resolved = computed_styles(
            pages[page], targets, ("color", "font-size", "font-weight", "opacity")
        )
        assert resolved is not None, page
        for name, selector, colour, px, bold, alpha in _BROWSER_CELLS:
            if name != page:
                continue
            got = resolved[selector]
            assert got, f"{page} {selector}: nothing on the page matches"
            assert got["color"] == colour, (page, selector, got["color"])
            assert float(got["font-size"].removesuffix("px")) == pytest.approx(
                px, abs=0.001
            ), (
                page,
                selector,
                got["font-size"],
            )
            assert (int(got["font-weight"]) >= 700) is bold, (page, selector)
            assert float(got["opacity"]) == pytest.approx(alpha), (page, selector)
