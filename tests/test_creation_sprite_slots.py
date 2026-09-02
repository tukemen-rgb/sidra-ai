"""A picture in a generated page can be swapped for a better one.

§9 学び (2) of the knowledge base: the generators people rate highest are
the ones whose art can be replaced. Installing a local image model is the
owner's own machine and their own decision - it is recorded in E and not
done here. What C-1116 builds is the receptacle, so that the day a model
exists the art is a file drop and not a rewrite.

The convention has three parts, and each is tested for the failure it
prevents rather than for its own existence:

* a slot is **declared**, so a page cannot grow a picture nobody can
  replace (the duel has called ``sprite('fighter')`` since it was written
  and nothing filled it - now that is written down, with the reason);
* a file an operator drops in **wins** over the procedural SVG, which is
  the whole mechanism;
* a slot with no file at all **costs the look, not the play**, which is
  why this is safe to ship before any model exists.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import (  # noqa: E402
    TEMPLATES,
    generate_game,
    validate_game_html,
)
from sidra_ai.creation.sprites import (  # noqa: E402
    REPLACEABLE_SUFFIXES,
    SLOT_ROLES,
    UNFILLED_SLOTS,
    contract_gaps,
    generate_sprites,
    loader_probe,
    resolve_slots,
    save_sprites,
    seed_for,
    slot_calls,
    slots_for,
)

KEYS = sorted(TEMPLATES)
WITH_ART = [key for key in KEYS if any(slot.generated for slot in slots_for(key))]


# ------------------------------------------------------------- declaration


@pytest.mark.parametrize("template", KEYS)
def test_the_page_and_the_declaration_agree(template: str) -> None:
    """Both directions are failures, for different reasons.

    A call with no slot is a picture nobody can replace and nobody can see
    is missing; a slot with no call is a file written into a project that
    nothing ever loads.
    """

    assert contract_gaps(template, TEMPLATES[template].script) == []


@pytest.mark.parametrize("template", KEYS)
def test_every_slot_says_what_it_is_for(template: str) -> None:
    """A slot's name is what the page calls it, not what a filler needs."""

    for slot in slots_for(template):
        assert slot.role, f"{template}/{slot.name} has no role written down"
        assert SLOT_ROLES[slot.name] == slot.role


def test_an_unfilled_slot_carries_its_reason() -> None:
    """Empty is allowed; empty-and-unexplained reads as an oversight."""

    for template, slots in UNFILLED_SLOTS.items():
        for name, why in slots.items():
            assert name in slot_calls(TEMPLATES[template].script)
            assert why.strip(), f"{template}/{name} is unfilled with no reason"


def test_the_duel_slot_is_declared_rather_than_filled() -> None:
    """The template draws its fighters on top of the slot, deliberately.

    Filling it with a procedural SVG would put art under the shapes that
    are already the fighter - near-invisible, and a change to a design
    decision rather than a receptacle for one.
    """

    assert "fighter" in UNFILLED_SLOTS["duel"]
    assert [slot.generated for slot in slots_for("duel")] == [False]


# ------------------------------------------------------------- replacement


@pytest.mark.parametrize("template", WITH_ART)
def test_the_generated_art_resolves(template: str, tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    save_sprites(generate_sprites(template, seed=seed_for(template)), assets)

    resolved = resolve_slots(template, assets)

    for slot in slots_for(template):
        if slot.generated:
            assert resolved[slot.name] == f"assets/{slot.name}.svg"


@pytest.mark.parametrize("template", WITH_ART)
def test_a_dropped_in_picture_wins(template: str, tmp_path: Path) -> None:
    """The receptacle itself: filling a slot is putting a file in a folder."""

    assets = tmp_path / "assets"
    save_sprites(generate_sprites(template, seed=seed_for(template)), assets)
    name = next(slot.name for slot in slots_for(template) if slot.generated)
    (assets / f"{name}.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    resolved = resolve_slots(template, assets)

    assert resolved[name] == f"assets/{name}.png"


def test_the_preference_order_puts_the_generated_file_last() -> None:
    """SVG is what is being replaced, so it can never win the tie."""

    assert REPLACEABLE_SUFFIXES[-1] == ".svg"


def test_a_directory_is_not_a_picture(tmp_path: Path) -> None:
    """``target.png/`` is a surprise, not an asset."""

    assets = tmp_path / "assets"
    save_sprites(generate_sprites("fishing", seed=1), assets)
    (assets / "target.png").mkdir()

    assert resolve_slots("fishing", assets)["target"] == "assets/target.svg"


def test_an_empty_directory_fills_nothing(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()

    assert resolve_slots("fishing", assets) == {}


# ---------------------------------------------------------------- fallback


def _loader(*, decoded: bool) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to run the page's own sprite loader")
    probe = subprocess.run(
        ["node", "-"],
        input=loader_probe(decoded=decoded),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_a_picture_that_never_decodes_leaves_the_flat_shape() -> None:
    """Why the receptacle is safe to ship before any model exists."""

    seen = _loader(decoded=False)

    assert seen["painted"] == ["#abcdef"]
    assert seen["drawn"] == 0


def test_a_decoded_picture_replaces_the_flat_shape() -> None:
    """The other direction: a loader that always fell back would be inert."""

    seen = _loader(decoded=True)

    assert seen["drawn"] == 1
    assert seen["painted"] == []


@pytest.mark.parametrize("template", KEYS)
def test_a_page_with_no_pictures_is_still_a_game(template: str) -> None:
    verdict = validate_game_html(generate_game("ゲームを作って", template=template).html)

    assert verdict["playable"], verdict["failures"]


@pytest.mark.parametrize("template", WITH_ART)
def test_the_page_loads_the_file_and_nothing_remote(
    template: str, tmp_path: Path
) -> None:
    assets = tmp_path / "assets"
    save_sprites(generate_sprites(template, seed=seed_for(template)), assets)
    resolved = resolve_slots(template, assets)

    page = generate_game("ゲームを作って", template=template, sprites=resolved).html

    for path in resolved.values():
        assert path in page
    assert "http://" not in page and "https://" not in page
