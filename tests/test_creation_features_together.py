"""All ten of them at once, in the same page, on the same frame.

C-1104 to C-1116 went in over twelve hours, each with a judge that drives
the page with its own feature on and the rest at their defaults. Nobody had
run the clock, the failure beat, the result strip, the daily seed, the
unlock, the share line, the panel and the instant start together - which is
the only way a person ever runs them.

The sweep found two defects that no single feature's judge could see:

* The result strip had grown to about 800px on a 720px canvas. Four
  features had each added a clause to it while the others were off, and
  being centre-aligned it lost both ends - the daily stamp on the left and
  the copy hint on the right.
* ``catch`` and ``fishing`` have no seed at all; their boards come out of
  ``Math.random``. With the daily switch on, both were saying 今日の挑戦 -
  on screen and in the line people paste - about a board nobody else had.

Both are fixed. These tests are what stops them coming back, and the third
kind - a storage key two features share - is asserted rather than waited
for.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import TEMPLATES, _DIFFICULTY, generate_game  # noqa: E402
from sidra_ai.creation.share import leaks  # noqa: E402
from sidra_ai.creation.skins import skin_spec  # noqa: E402
from sidra_ai.creation.together import (  # noqa: E402
    CANVAS_WIDTH,
    STORAGE_PREFIXES,
    key_gaps,
    probe_source,
    storage_keys,
    text_width,
)
from sidra_ai.creation.tuning import SPEED_BINDING  # noqa: E402

KEYS = sorted(TEMPLATES)
REQUEST = "ゲームを作って"
STAMP = "2026-09-03"
SEED = zlib.crc32(REQUEST.encode("utf-8"))
#: Templates whose board is not seeded and so cannot be shared. Empty
#: today: catch and fishing were the two, and C-1119 gave them seeded
#: boards rather than leaving them silent. Kept as a list rather than
#: deleted, because the rule outlives the case - a template written
#: tomorrow with no seed must not claim the day either, and the assertion
#: below is what would notice.
SEEDLESS: tuple[str, ...] = ()


def _script(template: str):
    art = generate_game(REQUEST, template=template)
    found = re.search(r"<script>(.*?)</script>", art.html, re.S)
    assert found is not None
    return found.group(1), art.title


def _everything(template: str) -> dict:
    """One page with every recent feature switched on, played out."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the page")
    body, _ = _script(template)
    earned = skin_spec(template)["skins"][1]
    hardest = max(pair[0] for pair in _DIFFICULTY[template].values())
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(
            body,
            speed_expr=SPEED_BINDING[template],
            stamp=STAMP,
            stored={
                f"sidra.seen.{template}": "1",
                f"sidra.skin.{template}": earned["id"],
                f"sidra.total.{template}": str(earned["at"]),
                f"sidra.best.{template}": "999999",
                f"sidra.tune.{template}": {"daily": True, "speed": hardest},
            },
        ),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def _band(seen: dict) -> list[str]:
    """The strip's own lines, told apart from the banner by where they sit."""

    return sorted({item["text"] for item in seen["strip"] if item["y"] >= 280})


# ------------------------------------------------------ the two defects found


@pytest.mark.parametrize("template", KEYS)
def test_the_result_strip_fits_on_the_canvas(template: str) -> None:
    """It did not. Four features each added a clause while the rest were off."""

    over = [
        item["text"]
        for item in _everything(template)["strip"]
        if text_width(item["text"]) > CANVAS_WIDTH
    ]

    assert over == [], f"{over[0] if over else ''} runs off a {CANVAS_WIDTH}px canvas"


@pytest.mark.parametrize("template", SEEDLESS)
def test_a_board_nobody_else_has_is_not_called_todays(template: str) -> None:
    """The rule, for any template that has no seed.

    The daily switch can be on and the board still be only this player's,
    so neither the screen nor the copied line may say otherwise - the whole
    value of the stamp is that it is everybody's. No template is in this
    state today; the parametrisation is empty on purpose, and the next test
    is what keeps it that way.
    """

    seen = _everything(template)

    assert seen["facts"]["round"]["seed"] is None, "this template grew a seed"
    assert not [line for line in _band(seen) if "今日の挑戦" in line]
    assert STAMP not in (seen["clipboard"][0] if seen["clipboard"] else "")


def test_the_claim_is_gated_on_having_a_board_at_all() -> None:
    """The mechanism behind the rule, since no template exercises it now.

    ``dailyBoard`` is the switch *and* a seed. Without the second half the
    page would go back to dating a board nobody else has, which is what
    C-1118 found catch and fishing doing.
    """

    from sidra_ai.creation.daily import DAILY_PREAMBLE

    assert "function dailyBoard(){" in DAILY_PREAMBLE
    assert "dailyOn()&&typeof SEED!=='undefined'" in DAILY_PREAMBLE


@pytest.mark.parametrize("template", KEYS)
def test_every_shipped_template_has_a_board_to_share(template: str) -> None:
    """C-1119: two of the ten used to lay their board out with Math.random,
    which left them unable to join the shared day honestly."""

    assert _everything(template)["facts"]["round"]["seed"] is not None


@pytest.mark.parametrize("template", KEYS)
def test_a_shared_board_still_says_so(template: str) -> None:
    """The fix must not have silenced the templates that do have a board."""

    seen = _everything(template)

    assert seen["facts"]["round"]["seed"] is not None
    assert [line for line in _band(seen) if "今日の挑戦" in line]
    assert STAMP in seen["clipboard"][0]


# ---------------------------------------------------- everything, at once


@pytest.mark.parametrize("template", KEYS)
def test_the_features_do_not_take_each_others_turns(template: str) -> None:
    seen = _everything(template)
    earned = skin_spec(template)["skins"][1]
    hardest = max(pair[0] for pair in _DIFFICULTY[template].values())

    # C-1111 opened it, and C-1105's beat has not fired a sound yet.
    assert seen["atLoad"]["gate"]["skipped"] is True
    assert seen["atLoad"]["gate"]["frames"] >= 1
    assert seen["atLoad"]["gate"]["gesture"] is False
    # C-1113's stored number survived C-1107's seed being switched on.
    assert seen["atLoad"]["speed"] == hardest
    # C-1109's colour is the one being painted with.
    assert seen["atLoad"]["accent"] == earned["accent"]
    # C-1104 still ends the round, and C-1106 still draws the way back.
    assert seen["atBreak"]["round"]["done"] or seen["atBreak"]["round"]["ended"]
    assert seen["stripAt"] is not None
    assert [line for line in _band(seen) if "もう一度" in line]


@pytest.mark.parametrize("template", KEYS)
def test_what_is_copied_is_still_safe_with_everything_on(template: str) -> None:
    _, title = _script(template)
    seen = _everything(template)

    assert seen["clipboard"], "nothing was copied from the result screen"
    assert leaks(seen["clipboard"][0], request=REQUEST, title=title, seed=SEED) == []


# ----------------------------------------------------------------- storage


@pytest.mark.parametrize("template", KEYS)
def test_no_two_features_share_a_storage_key(template: str) -> None:
    """Five features write to localStorage now. Two on the same key would
    destroy each other quietly - a best score that resets, a skin that
    un-earns itself."""

    body, _ = _script(template)

    assert key_gaps(body) == []
    assert set(storage_keys(body)) == set(STORAGE_PREFIXES)


@pytest.mark.parametrize("template", KEYS)
def test_every_write_stays_in_its_own_templates_namespace(template: str) -> None:
    """Otherwise two games in one browser would share a best score."""

    stray = [key for key in _everything(template)["writes"] if not key.endswith(f".{template}")]

    assert stray == []


def test_the_declared_keys_say_who_owns_each_one() -> None:
    """A feature picking an existing key should fail the sweep, not silently
    overwrite whichever feature got there first.

    This pinned the *number* of prefixes at first, which broke twice in one
    hour for two different loops adding a key they were entitled to add.
    The count was never the property worth holding: what matters is that
    each prefix is namespaced, says which item owns it, and cannot swallow
    another one. Whether the table has six entries or nine is not a fact
    about the product.
    """

    assert STORAGE_PREFIXES, "the contract cannot be empty"
    for prefix, owner in STORAGE_PREFIXES.items():
        assert prefix.startswith("sidra.") and prefix.endswith(".")
        assert "C-1" in owner, f"{prefix} does not say which item owns it"
        others = [other for other in STORAGE_PREFIXES if other != prefix]
        assert not [
            other for other in others if other.startswith(prefix) or prefix.startswith(other)
        ], f"{prefix} overlaps another declared key"
