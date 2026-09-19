"""C-1219: a generated game's control-panel buttons must be tappable on a phone.

The touch pad made the game itself playable on a phone, but the HTML panel
around it (skin picker, copy-result, key remap, reset) kept buttons 24-32px
tall - under the 48dp minimum the knowledge base the pad cites already sets.
No panel sets a button height inline, so one coarse-pointer rule in the
shared shell raises every one of them without touching the desktop layout
or the canvas-drawn pad.
"""

from __future__ import annotations

import re

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.touch_targets import evaluate_touch_targets


def test_touch_targets_eval_passes():
    result = evaluate_touch_targets()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 4


def test_coarse_pointer_button_rule_present_in_every_template():
    # The rule lives in the shared shell, so it rides every template.
    for request in ("魚を釣るゲーム", "猫がジャンプするゲーム", "パズルを作って", "シューティングを作って"):
        html = generate_game(request).html
        assert "@media (pointer:coarse)" in html
        assert re.search(r"@media\s*\(pointer:coarse\)\s*\{button\{min-height:48px\}", html)


def test_min_height_does_not_leak_to_desktop():
    """The FINGER's floor stays in the query; the 24px one is allowed.

    C-1968 narrowed this. WCAG 2.2 SC 2.5.8 (§40) asks for 24 x 24 CSS px
    on any pointer - a mouse included - and the shell now carries that as
    a base floor, measured in a real browser by
    ``creation_targets_meet_the_size_floor``. What this still pins is the
    thing C-1219 actually meant: a 48px button must not reach the desktop
    panel it was asked not to inflate.
    """

    html = generate_game("魚を釣るゲーム").html
    without_coarse = re.sub(
        r"@media\s*\(pointer:coarse\)\s*\{[^@]*?\}\}", "", html, flags=re.DOTALL
    )
    style = without_coarse.split("</style>")[0]
    over = [int(px) for px in re.findall(r"min-height:\s*(\d+)px", style) if int(px) > 24]
    assert over == [], over


def test_every_template_meets_the_size_floor_in_both_languages() -> None:
    """§40's floor across all twenty pages, not the two the collector reads.

    C-1969. ``creation_targets_meet_the_size_floor`` measures catch in two
    languages because a browser run a page is not free and the collector
    already sits near its advisory line. The panels come from one shell, so
    the other nine templates should follow - "should" being the word this
    test exists to replace. Measured once by hand at 502 targets across 20
    pages with none under the floor; held here so it stays that way.
    """

    import pytest

    from sidra_ai.evals.drawn_text_stays_on_the_canvas import (
        ENGLISH_ASKS,
        JAPANESE_ASKS,
    )
    from sidra_ai.evals.targets_meet_the_size_floor import CHROME, _measure, _under

    import pathlib

    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    under: list[str] = []
    counted = 0
    for asks in (ENGLISH_ASKS, JAPANESE_ASKS):
        for key, ask in sorted(asks.items()):
            items = _measure(generate_game(ask).html)
            assert items, f"{key}: nothing measured"
            counted += len(items)
            small, _bad = _under(items)
            under += [f"{key}: {name}" for name in small]
    assert under == [], under
    assert counted > 400, counted


def test_every_template_fits_320px_in_both_languages() -> None:
    """§41 across all twenty pages, not the two the collector reads (C-1971).

    ``creation_page_reflows_at_320px`` measures catch in two languages
    because a browser run is not free. The panel comes from one shell, so
    the other nine should follow - measured once at 20 pages, all 305/305
    with nothing past the edge, and held here so it stays true.
    """

    import pathlib

    import pytest

    from sidra_ai.evals.drawn_text_stays_on_the_canvas import (
        ENGLISH_ASKS,
        JAPANESE_ASKS,
    )
    from sidra_ai.evals.page_reflows_at_320px import _measure
    from sidra_ai.evals.targets_meet_the_size_floor import CHROME

    if not pathlib.Path(CHROME).exists():  # pragma: no cover - environment guard
        pytest.skip("no browser to measure with")

    flowed: list[str] = []
    for asks in (ENGLISH_ASKS, JAPANESE_ASKS):
        for key, ask in sorted(asks.items()):
            seen = _measure(generate_game(ask).html)
            assert "err" not in seen, f"{key}: {seen.get('err')}"
            if seen["scrollW"] > seen["vw"] + 1 or seen["count"]:
                flowed.append(f"{key}: {seen['scrollW']}/{seen['vw']}")
    assert flowed == [], flowed
