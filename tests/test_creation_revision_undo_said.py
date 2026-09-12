"""A revision says what it took back (§9 事実 2, C-1710).

§9 records the market's second complaint as 意図理解の低さと修正の副作用,
and §9's own 学び puts 生成後の対話的修正 on the list SIDRA has not won.
Measured, it was here: 「敵を減らして」 set the enemies to 2 and the reply
said so; 「難しくして」 one sentence later put them back to 4 and the reply
named only the difficulty.

Taking the band back is the design - the ladder owns both axes and the
newer instruction wins - and it stays that way. What changed is the
silence. The reply compared the new panel against a ``before_panel`` the
band had already been deleted from, so "never set" and "set, and just
discarded" were the same absence.

Held across 42 pairs of the seven axes before this was written: band
against difficulty is the only pair that takes anything back.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from sidra_ai.creation.games import generate_game, save_game
from sidra_ai.creation.revise import (
    build_game_reviser,
    detect_revision_intent,
    save_meta,
)

SAYS = "難易度に合わせて"


def dials(path: str | Path) -> dict:
    body = re.search(
        r"<script>(.*?)</script>", Path(path).read_text(encoding="utf-8"), re.S
    )
    assert body is not None
    spec = re.search(r"const TUNE_SPEC=(\{.*?\});", body.group(1), re.S)
    assert spec is not None
    return {f["key"]: f["default"] for f in json.loads(spec.group(1))["fields"]}


def conversation(sentences: list[str]) -> list[tuple[str | None, dict]]:
    """A real conversation from a fresh page, through the real reviser."""

    with tempfile.TemporaryDirectory() as home:
        built = generate_game("冒険ゲームを作って", template="adventure")
        page = save_game(built, home)
        save_meta(
            page,
            request="冒険ゲームを作って",
            template="adventure",
            difficulty=built.difficulty,
            theme="",
            title=built.title,
            panel={},
        )
        said: list[tuple[str | None, dict]] = [(None, dials(page))]
        revise = build_game_reviser(home)
        for sentence in sentences:
            out = revise(sentence, detect_revision_intent(sentence))
            assert out.artifact_path, sentence
            said.append((out.summary or "", dials(out.artifact_path)))
        return said


@pytest.mark.parametrize(
    ("first", "then"),
    [
        ("さっきのゲームの敵を減らして", "さっきのゲームを難しくして"),
        ("さっきのゲームの敵を増やして", "さっきのゲームをやさしくして"),
    ],
)
def test_the_reply_names_the_band_it_put_back(first: str, then: str) -> None:
    """Both directions of the ladder: a judge written on one of them would
    let the other go quiet."""

    talk = conversation([first, then])
    was, now = talk[1][1]["band"], talk[2][1]["band"]
    assert was != now, "the ladder no longer moves the band; nothing is measured here"
    said = talk[2][0] or ""
    assert SAYS in said, said
    assert f"{int(was)}→{int(now)}" in said, (was, now, said)


def test_nothing_set_means_nothing_claimed() -> None:
    """The other direction. A reply that says it every time would pass the
    test above and would be lying to everyone who never asked."""

    talk = conversation(["さっきのゲームを難しくして"])
    assert SAYS not in (talk[1][0] or ""), talk[1][0]


def test_the_dials_the_ladder_does_not_own_survive_it() -> None:
    """So that "taken back" keeps meaning the one thing it means."""

    talk = conversation(["さっきのゲームを赤にして", "さっきのゲームを難しくして"])
    assert talk[1][1]["accent"] == talk[2][1]["accent"], (
        talk[1][1]["accent"],
        talk[2][1]["accent"],
    )
    assert SAYS not in (talk[2][0] or ""), talk[2][0]


def test_the_number_said_is_the_number_the_page_got() -> None:
    """Read off the built page, not off the sentence - the reply could
    name a pair of numbers the ladder never actually used."""

    from sidra_ai.creation.games import _DIFFICULTY

    talk = conversation(["さっきのゲームの敵を減らして", "さっきのゲームを難しくして"])
    said = talk[2][0] or ""
    ladder = _DIFFICULTY["adventure"]["hard"][1]
    assert talk[2][1]["band"] == ladder, (talk[2][1]["band"], ladder)
    assert f"→{int(ladder)}" in said, said
