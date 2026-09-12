"""What a finger lands on is the row, not the control (§4, C-1681).

C-1234 floored the tuning panel's controls for a coarse pointer: 16px
type, 44px min-height on the select, the sliders and the colour picker,
and 24x24 on the checkboxes. ``evals/touch_form_controls.py`` pins those
declarations with a regex over the shell CSS, and its docstring says the
layout proof "runs at fix time and is recorded in the loop log" - the
same sentence C-1667 found in ``touch_targets.py`` (the floor was 18%
short) and C-1671 found in ``keys_dont_scroll.py`` (nine templates of ten
swallowed the panel's own keys).

Two things that regex cannot see. The panel is built at run time, so a
static read of the generated page finds one ``<button>`` and no controls
at all. And ``tuneControl`` wraps every control in a
``<label class="tune-row">``, which makes the whole line toggle it - so
the tap target is the row, and the row is as tall as its tallest child.

Measured before fixed, in Chromium at 390px with the coarse rules
applied: the slider, select and colour rows stood 44-48px and the six
checkbox rows 30-36px.

C-1712 adds the other half of §4 事実 1's sentence. 「大きく・間隔を空けて」
had its size half raised twice - C-1234 for the controls, C-1681 for the
row - and its spacing half never built at all: every row carried
``margin:6px 0``, which collapses between siblings into a 6px gap against
the 8dp 事実 2 asks for. Measured in a real browser at the fix: eleven
adjacent pairs, 6.00px every one; afterwards 10.00px every one, and all
twelve rows 48.00px tall.

The floor moved to 48 with it. 44 was the number the neighbouring
controls happened to get, and the judge was holding the panel to a floor
below the standard it quotes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.tuning import panel_probe

ROW_FLOOR = 48.0  # §4 事実 2's own number (C-1712); 44 was the neighbours'
ROW_GAP = 8.0  # and the other half of the same sentence

COARSE = re.compile(
    r"@media\s*\(\s*pointer\s*:\s*coarse\s*\)\s*\{(?P<body>.*?)\}\s*"
    r"(?:/\*|@media|</style)",
    re.S,
)


def _rules(page: str) -> list[tuple[list[str], dict[str, float]]]:
    found = COARSE.search(page)
    assert found is not None, "no coarse-pointer block on the page"
    out: list[tuple[list[str], dict[str, float]]] = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", found.group("body")):
        sizes = {
            prop: float(value)
            for prop, value in re.findall(r"([a-z-]+)\s*:\s*([0-9.]+)px", body)
            if prop in ("min-height", "height")
        }
        if sizes:
            out.append(([s.strip() for s in sel.split(",")], sizes))
    return out


def _matches(selector: str, kind: str, row: bool) -> bool:
    if selector in (".tune-row", "label.tune-row"):
        return row
    if row:
        return False
    tag = kind.split("[")[0]
    want = kind[kind.index("[") + 1 : -1] if "[" in kind else None
    if selector == tag:
        return want is None or tag != "input"
    got = re.fullmatch(r"input\[type=([a-z]+)\]", selector)
    return got is not None and tag == "input" and got.group(1) == want


def _floor(rules, kind: str, *, row: bool) -> float:
    best = 0.0
    for selectors, sizes in rules:
        if any(_matches(s, kind, row) for s in selectors):
            best = max(best, max(sizes.values()))
    return best


@pytest.fixture(scope="module")
def page() -> str:
    return generate_game("迷宮を冒険するゲームを作って").html


@pytest.fixture(scope="module")
def panel(page: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to build the panel")
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=panel_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])


def test_the_panel_is_not_in_the_page_until_it_runs(page: str) -> None:
    """Why the regex could not have seen any of this."""

    static = re.findall(r"<(select|textarea)\b", page)
    assert static == [], static
    assert 'type="checkbox"' not in page


def test_the_panel_really_builds_its_controls(panel: dict) -> None:
    counts = panel["counts"]
    assert counts.get("input[checkbox]", 0) >= 5, counts
    assert counts.get("input[range]", 0) >= 2, counts
    assert counts.get("select", 0) >= 1, counts
    assert len(panel["rows"]) >= 6, len(panel["rows"])


def test_every_row_a_finger_lands_on_clears_the_floor(
    page: str, panel: dict
) -> None:
    """The defect itself. A row's height is its tallest child's, so a
    checkbox row without a rule of its own stands at the checkbox's 24."""

    rules = _rules(page)
    row_floor = _floor(rules, "", row=True)
    short = []
    for row in panel["rows"]:
        kinds = row["controls"] or ["none"]
        tall = max([row_floor] + [_floor(rules, k, row=False) for k in kinds])
        if tall < ROW_FLOOR:
            short.append((row["tune"], kinds, tall))
    assert short == [], short


def test_the_row_is_what_the_finger_hits(panel: dict) -> None:
    """If a control were moved out of its label, only the 24px square
    would answer the tap and the row's floor would mean nothing."""

    assert panel["loose"] == [], panel["loose"]
    for row in panel["rows"]:
        assert row["controls"], row
        assert "tune-row" in row["className"], row


def test_the_rows_keep_their_distance(panel: dict) -> None:
    """The half of 「大きく・間隔を空けて」 that was never built. Adjacent
    siblings' vertical margins collapse, so the gap between two rows is
    the margin itself and not twice it."""

    gap = (panel.get("facts") or {}).get("rowGap")
    assert isinstance(gap, (int, float)), panel.get("facts")
    assert gap >= ROW_GAP, gap


def test_the_space_reported_is_the_space_applied(panel: dict) -> None:
    """Otherwise the test above is satisfied by a page that says 10 and
    styles 6 - which is the exact shape of the defect being closed."""

    gap = (panel.get("facts") or {}).get("rowGap")
    for row in panel["rows"]:
        assert f"margin:{int(gap)}px 0" in row["css"], (row["tune"], row["css"])


def test_the_space_is_named_once(page: str) -> None:
    """The style the page applies and the number the judge reads come from
    one constant, so they cannot drift apart (C-1342)."""

    from sidra_ai.creation import tuning

    assert "const TUNE_ROW_GAP=10;" in tuning.TUNE_PREAMBLE
    assert "+TUNE_ROW_GAP+'px 0'" in tuning.TUNE_PREAMBLE
    assert "margin:6px 0" not in tuning.TUNE_PREAMBLE


def test_the_floor_is_the_number_the_standard_quotes(page: str) -> None:
    """44 was the neighbours' number. §4 事実 2 says 48dp, and the button
    rule in the same coarse block has always used it."""

    found = COARSE.search(page)
    assert found is not None
    body = found.group("body")
    assert ".tune-row{min-height:48px}" in body, body
    assert "button{min-height:48px}" in body, body


def test_the_floor_is_not_read_from_outside_the_coarse_block(page: str) -> None:
    """Desktop keeps its compact panel: the row rule must live inside the
    coarse query, not at the top level where it would fatten every
    screen."""

    found = COARSE.search(page)
    assert found is not None
    assert ".tune-row" in found.group("body")
    outside = page[: found.start()] + page[found.end() :]
    assert ".tune-row{min-height" not in outside
