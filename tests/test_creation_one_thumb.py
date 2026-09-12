"""One thumb is enough - for nine of the ten (§8 事実 5, C-1698).

§8's fifth fact is Voodoo's shipping question: can this be played
one-handed, first time, on a crowded train? On a phone the pad is a
rectangle drawn inside the canvas, so "two inputs at once" means two
thumbs.

C-1691 measured it and found exactly one template that fails: the
platformer's jump carries no horizontal motion, so crossing a gap needs
a direction held *while* jumping. Its fix moves §3's soft-lock geometry
(C-1367's 19.9-32.9px), so the decision sits in the board's E section -
and until it lands, the other nine had no contract at all.

Two verbs needed rewriting to mean anything here. Racing drives itself,
so "reached the goal" happens with no input; the player's verb there is
steering. Duel ends the match when the player *loses*, so the verb is
the hit they landed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import THUMB_VERBS, generate_game, thumb_probe


def _play(key: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play one-handed")
    request, verb = THUMB_VERBS[key]
    html = generate_game(request).html
    found = re.search(r"<script>(.*?)</script>", html, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=thumb_probe(found.group(1), verb=verb),
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("key", sorted(THUMB_VERBS))
def test_one_thumb_lands_the_games_own_verb(key: str) -> None:
    seen = _play(key)
    assert seen["verb"], f"{key}: {seen.get('note')}"


def test_the_platformer_is_named_rather_than_hidden() -> None:
    """The one that fails is absent from the table on purpose, with the
    reason and the pending decision written down - not quietly dropped."""

    assert "platformer" not in THUMB_VERBS
    assert len(THUMB_VERBS) == 9


def test_the_driver_never_holds_two_keys() -> None:
    """The probe's own contract. If ``tap`` stopped releasing, every
    template would pass for the wrong reason."""

    from sidra_ai.creation import probekit

    assert "PROBE_THUMB" in probekit.__all__
    body = probekit.PROBE_THUMB
    assert "thumbEvent('keyup', thumbDown)" in body
    assert "function tap(k, frames){ hold(k, frames); release(); run(1) }" in body


def test_racing_and_duel_ask_for_the_players_own_verb() -> None:
    """Both games end on their own - racing by driving, duel by the
    player losing - so a verb that only reads "it ended" would pass a
    game nobody could steer or shoot."""

    assert "steered" in THUMB_VERBS["racing"][1]
    assert "state !== 'race'" not in THUMB_VERBS["racing"][1]
    assert "e.hp < foe0" in THUMB_VERBS["duel"][1]
