"""A colour the page spells out cannot know the theme (§4×§7, C-1722).

C-1131 took the default theme's ink out of every *word* and proved it by
running each template on the paper theme. That judge's own detail then
set the playfield aside - 「盤面の物（守衛の体力ピップ・路肩の標識・
ボスの被弾点滅）は対象外——形と色で情報を運ぶので、塗り替えは可読性の
判断」 - and the readability it named as the reason was never measured.

Measured: ``#dfe7f5``, which *is* gameyard's ink, was still spelled out
in eighteen playfield marks - the guardian's hit pips and smoke, the duel's
and kaiju's hurt flash, the platformer's flag pole. On the paper theme
they stand at 1.08:1 against the floor. The duel's clash flash was worse
still: ``#f5f7ff`` against a ``#f5f7fb`` floor is 1.00:1, a flash nobody
can see. The torch's ``#e8a33d`` was 1.87:1.

What this does NOT claim: that every mark clears 3:1 against its
neighbour. The paint recorder keeps colours and no coordinates, and a mark
drawn *on* another object legitimately sits close to the floor - a shadow
is 1.04:1 against a dark floor and is right to be. This holds the one
thing that is exactly checkable and was exactly wrong.
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.round import probe_source
from sidra_ai.creation.themes import DEFAULT_THEME, THEMES

SOURCES = {
    "adventure": "ADVENTURE_SCRIPT",
    "duel": "DUEL_SCRIPT",
    "kaiju": "KAIJU_SCRIPT",
    "platformer": "PLATFORMER_SCRIPT",
    "shooter": "SHOOTER_SCRIPT",
    "puzzle": "PUZZLE_SCRIPT",
    "marble": "MARBLE_SCRIPT",
    "racing": "RACING_SCRIPT",
}
#: racing's road edge is a deliberate two-tone pair (C-1287): a dark core
#: and a light rim, so one half always clears 3:1 against any paint. Named
#: rather than silently skipped, and measured by its own judge.
PAIRED = "const EDGE_A='#05070f',EDGE_B='#dfe7f5';"
INK = DEFAULT_THEME.tokens["text"].lower()


def body(key: str) -> str:
    module = importlib.import_module(f"sidra_ai.creation.{key}")
    return getattr(module, SOURCES[key])


def luminance(colour: str) -> float:
    colour = colour.lstrip("#")[:6]

    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(colour[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@pytest.mark.parametrize("key", sorted(SOURCES))
def test_no_template_spells_the_default_inks_literal(key: str) -> None:
    rest = body(key).replace(PAIRED, "").lower()
    spelled = f"'{INK}'"
    assert spelled not in rest, [
        line for line in rest.splitlines() if spelled in line
    ][:3]


def test_the_one_exemption_is_the_pair_it_says_it_is() -> None:
    """An exemption nobody re-reads is an allowlist. This one has to keep
    being the two-tone pair it was granted for."""

    assert PAIRED in body("racing")
    assert body("racing").replace(PAIRED, "").lower().count(f"'{INK}'") == 0


def test_the_marks_are_still_painted() -> None:
    """A fix that deleted them would satisfy the line above and lose the
    guardian's health."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    html = generate_game("紙のテーマで迷宮を冒険するゲームを作って").html
    found = re.search(r"<script>(.*?)</script>", html, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=probe_source(found.group(1)),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert got.returncode == 0, got.stderr[:400]
    seen = json.loads(got.stdout.strip().splitlines()[-1])
    colours = {str(p[1]).lower() for p in (seen.get("paint") or []) if isinstance(p[1], str)}
    assert colours, "nothing was painted, so nothing is proved"
    assert INK not in colours, INK


@pytest.mark.parametrize("name", sorted(THEMES))
def test_the_token_the_marks_now_use_reads_on_every_theme(name: str) -> None:
    """The replacement has to be worth making. Ink clears the floor on all
    four themes; the literal it replaced was 1.08:1 on one of them."""

    tokens = THEMES[name].tokens
    for floor in ("surface", "raised"):
        assert contrast(tokens["text"], tokens[floor]) >= 3.0, (name, floor)
        assert contrast(tokens["alert"], tokens[floor]) >= 3.0, (name, floor)
