"""Every template says whether the fight's loudness step applies to it (C-1882).

§6 観察 4 gave the step (C-1034). What it never gave was a place to say which
templates it applies to, so the classification lived inside the collector as
three literal sets - and they covered eight of the ten. ``marble`` and
``racing`` were in none of them: either could have claimed a fight or quietly
dropped the step and nothing would have gone red, while
``creation_combat_verified`` printed ten and said it had read 「the template's
own use of it」 for all of them.

The tables live next to ``combat()`` now, the way every sibling feature keeps
its own. These tests hold the shape that makes them worth having: a partition,
not three overlapping lists, and a reason in words for each template that is
left out.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.audio import (
    COMBAT_CONDITIONAL,
    COMBAT_FIGHTS,
    COMBAT_QUIET,
)
from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.ghost import GHOST_TEMPLATES, GHOST_UNWIRED


def _classes() -> dict[str, set[str]]:
    return {
        "fights": set(COMBAT_FIGHTS),
        "conditional": set(COMBAT_CONDITIONAL),
        "quiet": set(COMBAT_QUIET),
    }


def test_the_three_classes_partition_every_template_exactly_once() -> None:
    """Exactly once, both ways.

    Covering every template is not enough on its own - a template in two
    classes is a rule that contradicts itself - and neither is being disjoint,
    which an empty table satisfies. This is the same 「ちょうど一方に 1 度ずつ」
    the storage registry keeps (C-1734).
    """

    classes = _classes()
    counted = {
        key: sum(key in group for group in classes.values()) for key in TEMPLATES
    }
    assert all(count == 1 for count in counted.values()), {
        key: count for key, count in counted.items() if count != 1
    }
    everything = set().union(*classes.values())
    assert everything == set(TEMPLATES), everything ^ set(TEMPLATES)


def test_every_quiet_template_says_why_in_words() -> None:
    """A silent absence says neither 「not yet」 nor 「not applicable」.

    The sibling tables are the precedent, and ``GHOST_UNWIRED`` is checked
    here alongside so that the habit is what the test is about, not one
    table's spelling.
    """

    for key, reason in COMBAT_QUIET.items():
        assert len(reason) > 20, (key, reason)
        assert not reason.endswith("。"), key
    for key, reason in GHOST_UNWIRED.items():
        assert len(reason) > 20, (key, reason)
    assert set(GHOST_UNWIRED) | set(GHOST_TEMPLATES) == set(TEMPLATES)


def test_the_two_templates_the_old_sets_forgot_are_both_here() -> None:
    """Named, so that losing them again is a failing test rather than a gap."""

    assert "marble" in COMBAT_QUIET
    assert "racing" in COMBAT_QUIET


@pytest.mark.parametrize("template", sorted(COMBAT_QUIET))
def test_a_quiet_template_never_calls_the_step(template: str) -> None:
    """The table has to agree with the page, not only with itself.

    Read off the generated page rather than the module source: a template's
    script is assembled with shared preambles, and ``combat()`` is defined in
    one of them - so the question is whether this template's own code CALLS
    it, which is what the substring after the preamble boundary answers.
    """

    page = generate_game("ゲームを作って", template=template).html
    # `function combat(on)` is the preamble's definition; a call is what a
    # quiet template must not have. The definition is asserted separately so
    # that a page shipping no `combat(` at all - a broken preamble - cannot
    # pass this for the wrong reason. `combatOn(` does not contain `combat(`.
    assert "function combat(on)" in page, template
    calls = page.count("combat(") - page.count("function combat(")
    assert calls == 0, (template, calls)


@pytest.mark.parametrize("template", sorted(set(COMBAT_FIGHTS) | set(COMBAT_CONDITIONAL)))
def test_a_fighting_template_calls_the_step(template: str) -> None:
    page = generate_game("ゲームを作って", template=template).html
    calls = page.count("combat(") - page.count("function combat(")
    assert calls >= 1, template
