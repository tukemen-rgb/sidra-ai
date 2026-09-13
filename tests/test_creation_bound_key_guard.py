"""割り当て直したキーは、ページを流さない (§12 × §4, C-1759).

C-1671 put "this page's keys do not scroll it" into all ten templates
after measuring a board pushed 208px off screen in six presses. The guard
it wrote carries a literal list of the five keys the product ships with,
and - as its own comment says - is installed on the native listener
*before the remap wrapper exists*.

So the table an operator writes was never in the guard's view. Bind
PageDown to 「右」 and the cursor moves **and** the page scrolls: one key
doing two things, which is the same breakage C-1671 fixed, arriving
through the door C-1671 left open.

Tab is refused outright instead. Stopping a bound key's default is the
whole point of binding it, and a stopped Tab no longer reaches 「既定に
戻す」 - a setting nobody can leave, which is what WCAG 2.1.2 is named
after.

Both directions: a bound key's default stops, an unbound key's does not.
Without the second, "prevent everything" passes and breaks the page
around the game.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.remap import guard_probe

#: Three shapes of control table, because the spare key is bound to the
#: page's own first action: arrows both ways, arrows up/down only, and a
#: template whose only control is Space. A probe that named one action
#: was refused by the last two - the product being right and the driving
#: being wrong (C-1744's lesson, met again).
SAMPLE = ("puzzle", "duel", "fishing")


def _guard(template: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to press the keys")
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S)
    assert body is not None
    probe = subprocess.run(
        ["node", "-"],
        input=guard_probe(body.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", SAMPLE)
def test_an_unbound_spare_key_keeps_its_default(template: str) -> None:
    """Nothing is taken before anybody asks for it."""

    assert _guard(template)["before"]["spare"] is False


@pytest.mark.parametrize("template", SAMPLE)
def test_a_bound_key_loses_its_default(template: str) -> None:
    """The defect: the cursor moved and the board scrolled away."""

    seen = _guard(template)
    assert seen["bound"]["spare"] is True, "the binding was not accepted"
    assert seen["after"]["spare"] is True, "割り当てたキーがページも流す"


@pytest.mark.parametrize("template", SAMPLE)
def test_a_key_nobody_bound_still_keeps_its_default(template: str) -> None:
    """Without this, "prevent everything" scores full marks."""

    assert _guard(template)["after"]["unbound"] is False


@pytest.mark.parametrize("template", SAMPLE)
def test_tab_is_refused_and_stays_the_browsers(template: str) -> None:
    seen = _guard(template)
    assert seen["bound"]["tab"] is False, "Tab の割り当てを受けた"
    assert seen["after"]["tab"] is False, "断ったのに既定を止めた"


@pytest.mark.parametrize("template", SAMPLE)
def test_c1671_did_not_regress(template: str) -> None:
    """The two halves of the rule this item extends, in the same run."""

    seen = _guard(template)
    assert seen["after"]["canonical"] is True, "元からの矢印が止まらない"
    assert seen["after"]["inForm"] is False, "フォームに焦点があるのに奪った"


@pytest.mark.parametrize("template", SAMPLE)
def test_the_action_comes_from_the_page(template: str) -> None:
    """Templates do not read the same controls, and the probe asks."""

    target = _guard(template)["before"]["target"]
    assert isinstance(target, str) and target, template


def test_the_refusal_is_written_down_with_its_reason() -> None:
    """A refusal nobody can find a reason for becomes a bug report."""

    import inspect

    from sidra_ai.creation import remap

    source = inspect.getsource(remap)
    assert "REMAP_REFUSED" in source
    assert "2.1.2" in source, "keyboard trap の根拠が書かれていない"


def test_every_template_carries_the_shared_guard() -> None:
    """One predicate, not ten copies drifting apart (C-1342)."""

    for template in sorted(TEMPLATES):
        page = generate_game("ゲームを作って", template=template).html
        assert "function keyDrivesGame(" in page, template
        assert page.count("function keyDrivesGame(") == 1, template
