"""C-1431: the model's wording lands whole, and only where it belongs.

``with_copy`` overlays a model-written title and subtitle onto a page that
already works. Since C-1259 the subtitle names the genre in Japanese, so
the two fields can share a word - 「釣りゲームを作って」 titles its page
「釣り」 and its subtitle reads 「ジャンル 釣り」 - and a bare substitution
over the whole page lets whichever pass runs first cut into the other.

Measured on a fishing page, where the title's text occurs five times:

* three are display copy - the browser tab, the heading, the subtitle -
  and must follow the model;
* ``GTITLE="タイミング釣り"`` merely *contains* the title, and the share
  spec's ``name`` is 「釣り」 because that is the genre. Neither is the
  title, and a substitution wide enough to catch the display copy rewrites
  both without saying so.

Ordering the two passes closes one direction only, which is why the cases
below run both and then both at once.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.creation.games import generate_game

ASK = "釣りゲームを作って"

#: (label, model title, model subtitle)
CASES = (
    ("forward", "朝凪の一本", "潮が動く前に。"),
    ("reverse", "朝凪の一本", "釣りの朝に。"),
    ("both", "釣りの一日", "釣りの朝に。"),
)


@pytest.fixture(scope="module")
def page():
    made = generate_game(ASK)
    assert made.title in made.tagline, "the collision these pin is gone"
    return made


@pytest.mark.parametrize("label,title,tagline", CASES)
def test_the_display_copy_is_the_models(page, label, title, tagline) -> None:
    rewritten = page.with_copy(title=title, tagline=tagline)

    assert re.search(r"<title>(.*?)</title>", rewritten.html).group(1) == title
    assert re.search(r"<h1>(.*?)</h1>", rewritten.html).group(1) == title
    assert re.search(r'<p class="tag">(.*?)</p>', rewritten.html).group(1) == tagline
    assert page.tagline not in rewritten.html


@pytest.mark.parametrize("label,title,tagline", CASES)
def test_what_only_looks_like_the_title_is_left_alone(page, label, title, tagline) -> None:
    """The half a wider substitution silently gets wrong."""

    before = {
        pat: re.search(pat, page.html).group(1)
        for pat in (r'GTITLE="(.*?)"', r'"name": "(.*?)"')
    }

    rewritten = page.with_copy(title=title, tagline=tagline)

    for pat, kept in before.items():
        assert re.search(pat, rewritten.html).group(1) == kept, pat


def test_an_empty_overlay_still_changes_nothing(page) -> None:
    assert page.with_copy() is page
    assert page.with_copy(title="  ", tagline="  ") is page
