"""C-1425: the adventure says why the go ended.

The counters were never the hard part - reaching a loss was, which is what
C-1424 had to build first. What is checked here is that the two counters
are wired to the two damage sites they claim, and that the line the strip
draws is a comparison between them rather than the only clause the page
could ever reach.

The guardian's clause cannot be reached by playing: no drive that exists
today survives rooms 0 and 1 to meet it (C-1424 measured why). So it is
interrogated instead - the counters are moved and the same page is asked
again. That is a weaker claim than "seen in play" and is written down as
one: it says the comparison works, not that a guardian death has happened.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.recap import LOSS_UNWIRED, LOSS_WIRED, WIN_STATE, probe_source
from sidra_ai.evals.adventure_losable import REQUEST, recap_probe_source


def test_the_template_is_wired_rather_than_excused() -> None:
    # The old reason - "no counter survives it" - stopped being true the
    # moment the two counters existed, and a stale excuse is worse than
    # none: it tells the next reader not to look.
    assert "adventure" in LOSS_WIRED
    assert "adventure" not in LOSS_UNWIRED
    assert WIN_STATE["adventure"] == "win"
    assert len(LOSS_WIRED["adventure"]["causes"]) == 2


def test_a_probe_without_a_route_is_unchanged() -> None:
    # Six templates lose without being steered, and none of them should
    # notice that the hook exists.
    plain = probe_source("/* page */", template="shooter")
    assert "ROUTE_SETUP_TOKEN" not in plain
    assert "ROUTE_STEP_TOKEN" not in plain
    assert "advAim" not in plain


@pytest.fixture(scope="module")
def driven():
    """One real losing go, and the three questions asked of it afterwards."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    found = re.search(r"<script>(.*?)</script>", generate_game(REQUEST).html, re.S)
    assert found is not None
    run = subprocess.run(
        ["node", "-"],
        input=recap_probe_source(found.group(1)),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert run.returncode == 0, run.stderr[:400]
    out = run.stdout.strip().splitlines()
    return json.loads(out[-2]), json.loads(out[-1])


def test_the_driven_go_is_a_loss_with_a_reason(driven) -> None:
    main, _ = driven
    assert main["atEnd"]["lost"]
    assert main["atEnd"]["line"]
    assert not main["verdictWhileLive"]


def test_the_counters_agree_with_the_hearts(driven) -> None:
    # The same go, measured the other way: hearts watched frame by frame,
    # with the room each drop happened in. Rooms 0 and 1 have no guardian.
    _, tail = driven
    hits = tail["hits"]
    assert hits, "the hero never lost a heart"
    assert tail["roam"] == sum(1 for h in hits if h["room"] != 2)
    assert tail["guard"] == sum(1 for h in hits if h["room"] == 2)


def test_the_line_reports_that_count_and_reaches_the_strip(driven) -> None:
    main, tail = driven
    line = main["atEnd"]["line"]
    assert str(tail["roam"]) in line
    assert line in main["strip"]


def test_a_cause_counted_zero_is_not_named(driven) -> None:
    _, tail = driven
    assert tail["guard"] == 0
    assert "番人" not in tail["said"]


def test_the_largest_cause_is_a_comparison(driven) -> None:
    # Move the guardian above the roamers and the same page names the
    # guardian - with the moved count, not the one it had already printed.
    _, tail = driven
    assert "番人" in tail["saidGuard"]
    assert str(tail["roam"] + 5) in tail["saidGuard"]


def test_both_causes_at_zero_says_nothing(driven) -> None:
    _, tail = driven
    assert tail["saidNothing"] == ""


def test_a_win_is_not_explained(driven) -> None:
    main, _ = driven
    assert main["afterWin"]["lost"] is False
    assert main["afterWin"]["line"] == ""
