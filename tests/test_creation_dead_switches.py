"""A switch nothing reads is not an edit the operator can make (C-1729).

§9 学び (4) asks for editing means a non-engineer can use, and the tuning
panel is this product's answer: a form inside the generated page that
turns the difficulty, the two axes, the accent, the volume. C-1119 wrote
the rule one level down - a value nothing reads is not a fact about the
product - and this is the same rule one level up.

``panel_schema`` returned the same twelve rows for all ten templates.
Only ``racing``/``marble``/``platformer`` *call* ``ghostSample(`` - the
other seven are listed in ``ghost.GHOST_UNWIRED`` **with the reason each
one has no trail** - and only the duel reads ``tuneFlag('latch'``, which
the panel's own comment said out loud ("the duel's charge is exactly
that"). So sixteen of the offered switches asked the player to reload the
page and then changed nothing. The source knew; the panel did not.

The fix is C-1342's shared-constant rule: the table that decides whether
a row is drawn *is* the table that decides whether it is wired -
``GHOST_TEMPLATES`` and ``LATCH_TEMPLATES``, each living beside the
behaviour it describes.

Both directions are checked here and in ``creation_param_panel``. One
direction alone is passed by "offer nothing anywhere", which would delete
the working ghost switch from the three templates that have a ghost.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.creation.duel import LATCH_TEMPLATES
from sidra_ai.creation.games import TEMPLATES, _DIFFICULTY, generate_game
from sidra_ai.creation.ghost import GHOST_TEMPLATES, GHOST_UNWIRED
from sidra_ai.creation.tuning import panel_schema

#: The row key, the call the page makes when it actually reads it, and
#: the table that is allowed to decide which templates get the row.
#:
#: Measured, not deduced, and the measurement moved the mark: a plain
#: search for ``ghostSample(`` matches all ten pages, because the whole
#: ghost runtime - ``ghostOn``, ``ghostBucket``, ``ghostSample``,
#: ``ghostAt``, ``ghostBank`` - is injected into every page and only
#: *called* by three. The definition is not the wiring. So a call is an
#: occurrence that is not the ``function`` that declares it, which
#: separates 2 from 1 exactly.
WIRED = (
    ("ghost", "ghostSample(", re.compile(r"(?<!function )\bghostSample\("), GHOST_TEMPLATES),
    ("latch", "tuneFlag('latch'", re.compile(r"(?<!function )\btuneFlag\('latch'"), LATCH_TEMPLATES),
)

KEYS = sorted(TEMPLATES)


def _rows(template: str) -> list[str]:
    return [
        field["key"]
        for field in panel_schema(
            template,
            _DIFFICULTY[template],
            difficulty="normal",
            accent="#000000",
        )["fields"]
    ]


def _body(template: str) -> str:
    page = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None, f"{template}: no script in the page"
    return script.group(1)


@pytest.mark.parametrize("template", KEYS)
@pytest.mark.parametrize("row,mark,call,table", WIRED, ids=[row for row, _, _, _ in WIRED])
def test_the_row_is_offered_exactly_when_the_page_reads_it(template, row, mark, call, table):
    """Both directions in one assertion, for every template.

    Written as an equality rather than as two tests guarded by skips: a
    skip proves nothing, and the implementation that deletes the rows
    *and* stops calling would skip its way past both halves.

    (a) offered and not read - the defect this item fixes: a switch that
    reloads the page and changes nothing.
    (b) read and not offered - the same defect the other way up, and the
    one that lets "delete every row" score full marks.
    """

    offered = row in _rows(template)
    wired = call.search(_body(template)) is not None
    if offered and not wired:
        raise AssertionError(
            f"{template}: パネルは {row} を出すのに、ページは {mark} を呼ばない"
            " - 読み直させておいて何も変わらないスイッチ"
        )
    if wired and not offered:
        raise AssertionError(
            f"{template}: ページは {mark} を呼ぶのに、パネルが {row} を出さない"
            " - 動く機能を操作者から隠している"
        )


@pytest.mark.parametrize("row,mark,call,table", WIRED, ids=[row for row, _, _, _ in WIRED])
def test_the_row_table_is_the_wiring_table(row, mark, call, table):
    """C-1342: one table, not two that have to be kept in step by hand."""

    wired = {key for key in KEYS if call.search(_body(key))}
    assert wired == set(table), (
        f"{row}: 配線されているのは {sorted(wired)} なのに"
        f" 表は {sorted(table)} と言っている"
    )
    offered = {key for key in KEYS if row in _rows(key)}
    assert offered == set(table), (
        f"{row}: 行を出しているのは {sorted(offered)} で表と違う"
    )


def test_no_row_is_dropped_from_every_template():
    """A row that exists for nobody is a row that should be deleted.

    The failure this item fixes and the laziest fix for it look the same
    from one side, so the shape of the answer is pinned: each of these
    rows still reaches at least one template, and the difference between
    templates is real.
    """

    for row, _mark, _call, table in WIRED:
        assert table, f"{row} は誰にも出ていない - 行ごと消すべき"
        assert set(table) != set(KEYS), (
            f"{row} が全型に出ているなら、型で分ける意味が無い"
        )


def test_the_unwired_templates_carry_their_reason():
    """The seven without a ghost were already explained; keep them so.

    ``GHOST_UNWIRED`` is why this item could be decided from the source
    rather than guessed: the file had written down, for each template,
    what a progress-indexed trail would have to be indexed by. A later
    item that wires one of them starts from that sentence.
    """

    missing = sorted(set(KEYS) - set(GHOST_TEMPLATES) - set(GHOST_UNWIRED))
    assert not missing, f"ゴーストが無い理由が書かれていない型: {missing}"
    for key, why in GHOST_UNWIRED.items():
        assert key not in GHOST_TEMPLATES, f"{key} は配線済みなのに未配線の理由がある"
        assert len(why) > 20, f"{key} の理由が説明になっていない: {why!r}"
