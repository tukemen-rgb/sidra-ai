"""Every lock in the dungeon refuses the player without its key (C-1887).

§3 names four kinds of key - a tool, an ability, a piece of knowledge, an
event flag - and adventure ships one of each. §34 事実 1 says a lock is only a
lock if the player who lacks the key cannot open it. Before this, one of the
six was checked.
"""

from __future__ import annotations

from sidra_ai.evals.adventure_locks_hold import (
    LOCKS,
    evaluate_adventure_locks_hold,
)


def test_all_five_locks_hold_both_ways() -> None:
    result = evaluate_adventure_locks_hold()
    assert result.failures == ()
    assert result.passed
    assert result.held == len(LOCKS) == 5
    assert result.checks_total == result.checks_passed + len(result.failures)


def test_the_knowledge_key_is_one_of_them() -> None:
    """§3's least obvious key, and the one a tile-shaped judge nearly misses.

    The stone says an order and the marks answer to it; nothing is carried,
    nothing is unlocked by an item. If this ever leaves the list, the judge
    has quietly narrowed to keys you can hold.
    """

    result = evaluate_adventure_locks_hold()
    assert "stone_order" in result.locks
    assert dict(LOCKS)["stone_order"].endswith("順番を知っていること")


def test_the_grass_lock_is_left_to_the_judge_that_plays() -> None:
    """Two judges over one lock is two things to keep in step.

    C-1626 drives a real playthrough and shows that cutting through beats
    going around - a property this judge, which never moves the hero by
    playing, could not measure anyway.
    """

    assert not any(key.startswith("grass") for key, _name in LOCKS)


def test_the_probe_does_not_take_a_name_the_page_uses() -> None:
    """The page has its own ``knock(mark, tx, ty)``.

    A probe that declares ``function knock`` replaces it, the page's
    ``swing()`` then calls the probe's version, and the run eats its own
    stack. Measured the hard way while writing this - the same collision as a
    probe declaring ``let score`` beside a page that already has one.
    """

    from sidra_ai.evals.adventure_locks_hold import _PROBE

    assert "function knock(" not in _PROBE
    assert "function _probeKnock(" in _PROBE
